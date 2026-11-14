import hashlib
import json
import re
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid7

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from hibi.ai.classification import (
    CAPTURE_QUESTION_VERSION,
    CaptureClassifier,
    ClarificationGenerator,
    normalize_clarification_text,
)
from hibi.ai.embedding import Embedding, TextEmbedder
from hibi.modules.captures.errors import (
    CaptureNotEditableError,
    CaptureNotFoundError,
    CaptureNotRetryableError,
    CaptureTextInvalidError,
    IdempotencyKeyConflictError,
    IdempotencyKeyInvalidError,
    IdempotencyKeyRequiredError,
    MalformedCursorError,
    ScenarioNotAcceptableError,
)
from hibi.modules.captures.policies import (
    CAPTURE_ROUTE_CLARIFY,
    CAPTURE_ROUTE_POLICY_VERSION,
    CAPTURE_ROUTE_REMINDER,
    decide_capture_route,
    normalize_classification,
    normalize_urgency_score,
    propose_capture_scenario,
)
from hibi.modules.captures.repository import CaptureRepository
from hibi.modules.captures.search import rank_capture_by_keyword, rank_captures_by_semantic
from hibi.modules.captures.today import rank_today
from hibi.modules.captures.types import (
    CAPTURE_SEARCH_LIMIT,
    CAPTURE_SEARCH_MODE_SEMANTIC,
    CAPTURE_STATUS_COMPLETED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PENDING,
    CAPTURE_STATUS_PROCESSING,
    Capture,
    CapturePage,
    CreateCaptureCommand,
    CreateCaptureResult,
    ListCapturesQuery,
    SearchCapturesQuery,
    TodayCapturesQuery,
    UpdateCaptureCommand,
)
from hibi.modules.profiles.repository import ProfileRepository

_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[\x20-\x7E]{8,128}$")
_MAX_CAPTURE_LENGTH = 2_000


def _utc_now() -> datetime:
    """現在時刻を、UTC の aware な datetime で返す。"""
    return datetime.now(UTC)


class CaptureService:
    """Capture の作成、参照、更新、削除、AI 処理、検索をまとめるサービス。

    DB アクセスは repository に、分類や埋め込みは AI クライアントに任せる。
    ここでは入力の検証、冪等性の判定、処理の順序を決める。
    """

    def __init__(
        self,
        session: AsyncSession,
        repository: CaptureRepository,
        classifier: CaptureClassifier,
        generator: ClarificationGenerator,
        embedder: TextEmbedder,
        profiles: ProfileRepository,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        """サービスが使う依存を受け取って保持する。

        Args:
            session: 冪等キー衝突時の rollback に使うセッション。
            repository: Capture の永続化。
            classifier: Capture の分類。
            generator: 確認質問の生成。
            embedder: 本文とクエリのベクトル化。
            profiles: ユーザーのタイムゾーンの取得。
            clock: 現在時刻の取得元。シナリオの期限を決める基準になる。
                テストで固定時刻を差し込めるよう、引数にしている。
        """
        self._session = session
        self._repository = repository
        self._classifier = classifier
        self._generator = generator
        self._embedder = embedder
        self._profiles = profiles
        self._clock = clock

    async def create_capture(self, command: CreateCaptureCommand) -> CreateCaptureResult:
        """Capture を作成する。同じ冪等キーと本文の再送なら、既存の Capture を返す。

        本文は前後の空白を除いてからハッシュ化し、冪等キーに紐づけて比べる。
        同時リクエストで先に保存された場合は IntegrityError になるので、
        rollback して取り直し、再送か衝突かを改めて判定する。

        Args:
            command: 所有者、本文、冪等キー。

        Returns:
            Capture と、新規作成かどうか。再送なら created は False。

        Raises:
            IdempotencyKeyRequiredError: 冪等キーが未指定または空。
            IdempotencyKeyInvalidError: 冪等キーが形式に合わない。
            CaptureTextInvalidError: 本文が空、または長すぎる。
            IdempotencyKeyConflictError: 同じキーで本文が違う。
        """
        idempotency_key = command.idempotency_key
        if idempotency_key is None or idempotency_key == "":
            raise IdempotencyKeyRequiredError()
        if _IDEMPOTENCY_KEY_PATTERN.fullmatch(idempotency_key) is None:
            raise IdempotencyKeyInvalidError()

        stripped_raw_text = self._normalize_raw_text(command.raw_text)

        request_hash = hashlib.sha256(stripped_raw_text.encode("utf-8")).hexdigest()

        existing = await self._repository.get_by_idempotency_key(
            command.user_id, key=idempotency_key
        )
        result = self._replay_or_conflict(existing, request_hash)
        if result is not None:
            return result

        try:
            new = await self._repository.create_capture(
                command.user_id,
                capture_id=uuid7(),
                raw_text=stripped_raw_text,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                outbox_id=uuid7(),
            )
            return CreateCaptureResult(capture=new, created=True)
        except IntegrityError:
            await self._session.rollback()

            existing = await self._repository.get_by_idempotency_key(
                command.user_id, key=idempotency_key
            )
            result = self._replay_or_conflict(existing, request_hash)
            if result is not None:
                return result
            raise

    async def get_capture(self, user_id: UUID, capture_id: UUID) -> Capture:
        """所有者の Capture を 1 件返す。

        他人の Capture は存在を知らせないため、存在しない場合と同じ扱いにする。

        Args:
            user_id: 所有者。
            capture_id: 取得する Capture。

        Returns:
            該当の Capture。

        Raises:
            CaptureNotFoundError: 存在しない、または他人の Capture。
        """
        result = await self._repository.get_by_id(user_id, capture_id=capture_id)
        if result is None:
            raise CaptureNotFoundError(capture_id)
        return result

    async def list_captures(self, query: ListCapturesQuery) -> CapturePage:
        """所有者の Capture を、新しい順にカーソルでページングして返す。

        limit は 1 から 50 に丸め、未指定なら 20 にする。次ページの有無を
        知るため、1 件多く取得してから切り詰める。

        Args:
            query: 所有者、件数、前ページの続きを示すカーソル。

        Returns:
            Capture の一覧と、次ページのカーソル。

        Raises:
            MalformedCursorError: カーソルが壊れている。
        """
        limit = 20 if query.limit is None else query.limit
        limit = min(max(limit, 1), 50)

        start_created_at = None
        start_capture_id = None
        if query.cursor is not None and query.cursor != "":
            start_created_at, start_capture_id = self._decode_cursor(query.cursor)

        rows = await self._repository.list_for_user(
            query.user_id,
            limit=limit + 1,
            start_created_at=start_created_at,
            start_capture_id=start_capture_id,
        )
        items = rows[:limit]
        has_next_page = len(rows) > limit
        next_cursor = None
        if has_next_page:
            last = items[-1]
            next_cursor = self._encode_cursor(last.created_at, last.id)

        return CapturePage(items=items, next_cursor=next_cursor, has_next_page=has_next_page)

    async def list_today_captures(self, query: TodayCapturesQuery) -> list[Capture]:
        """今日やることを、優先度の高い順に最大 limit 件の Capture で返す。

        所有者の未完了のシナリオを候補として読み、ユーザーの timezone の暦日で
        今日の終わりを決めて、順位付けを `rank_today` に任せる。期限が今日の終わり
        以降の行は除く。期限が過ぎた行は、日付に関係なく含める。現在時刻は
        `clock` から、timezone はプロフィールから読む。プロフィールが無いか、
        名前が不正なら UTC として扱う。

        候補が無ければ、Capture を読まずに空のリストを返す。

        Args:
            query: 所有者と、返す最大件数。

        Returns:
            優先度の高い順の Capture。シナリオを含む。0 件なら空のリスト。
        """

        timezone = await self._profiles.get_timezone(query.user_id)
        candidates = await self._repository.list_open_scenario_candidates(query.user_id)
        ranked_candidate_ids = rank_today(
            candidates, now=self._clock(), timezone=timezone, limit=query.limit
        )
        if not ranked_candidate_ids:
            return []
        captures = await self._repository.list_captures_by_ids(
            user_id=query.user_id, capture_ids=ranked_candidate_ids
        )
        by_id = {capture.id: capture for capture in captures}
        return [by_id[capture_id] for capture_id in ranked_candidate_ids if capture_id in by_id]

    async def search_captures(self, query: SearchCapturesQuery) -> list[Capture]:
        """所有者の完了済みCaptureを、近い順に最大 CAPTURE_SEARCH_LIMIT 件返す。

        順位付けは search.py に任せる。mode が semantic ならクエリ文だけを
        embedder でベクトル化し、保存済みの embedding と比べる。本文の
        embedding は作り直さない。それ以外は TF-IDF のキーワード検索。
        0件なら空リストを返し、例外にはしない。

        Args:
            query: 所有者、検索語、検索方式。

        Returns:
            順位の高い順の Capture。scenario も含む。
        """

        documents = await self._repository.list_search_documents(query.user_id)

        if query.mode == CAPTURE_SEARCH_MODE_SEMANTIC:
            ranked = await rank_captures_by_semantic(
                documents, user_id=query.user_id, query=query.q, embedder=self._embedder
            )
        else:
            ranked = rank_capture_by_keyword(documents, user_id=query.user_id, query=query.q)
        capture_ids = ranked[:CAPTURE_SEARCH_LIMIT]
        if not capture_ids:
            return []

        captures = await self._repository.list_captures_by_ids(
            query.user_id, capture_ids=capture_ids
        )
        by_id = {capture.id: capture for capture in captures}
        return [by_id[capture_id] for capture_id in capture_ids if capture_id in by_id]

    async def update_capture(self, command: UpdateCaptureCommand) -> Capture:
        """Capture の本文を更新する。

        更新できる状態かどうかは repository の更新条件で判定する。
        更新できなかったときだけ読み直し、存在しないのか、編集できない
        状態なのかを区別する。

        Args:
            command: 所有者、対象の Capture、新しい本文。

        Returns:
            更新後の Capture。

        Raises:
            CaptureTextInvalidError: 本文が空、または長すぎる。
            CaptureNotFoundError: 存在しない、または他人の Capture。
            CaptureNotEditableError: 編集できない状態の Capture。
        """
        stripped_raw_text = self._normalize_raw_text(command.raw_text)

        updated = await self._repository.update_capture(
            command.user_id, capture_id=command.capture_id, raw_text=stripped_raw_text
        )

        if updated is not None:
            return updated

        current = await self._repository.get_by_id(command.user_id, capture_id=command.capture_id)
        if current is None:
            raise CaptureNotFoundError(capture_id=command.capture_id)

        raise CaptureNotEditableError()

    async def delete_capture(self, user_id: UUID, capture_id: UUID) -> None:
        """所有者の Capture を削除する。

        Args:
            user_id: 所有者。
            capture_id: 削除する Capture。

        Raises:
            CaptureNotFoundError: 存在しない、または他人の Capture。
        """
        is_deleted = await self._repository.delete_capture(user_id, capture_id=capture_id)
        if not is_deleted:
            raise CaptureNotFoundError(capture_id=capture_id)

    async def retry_capture(self, user_id: UUID, capture_id: UUID) -> Capture:
        """失敗した Capture の AI 処理を、もう一度キューに載せる。

        再試行できる状態かどうかは repository の更新条件で判定する。
        再試行できなかったときだけ読み直し、存在しないのか、再試行できない
        状態なのかを区別する。

        Args:
            user_id: 所有者。
            capture_id: 再試行する Capture。

        Returns:
            再試行を受け付けた後の Capture。

        Raises:
            CaptureNotFoundError: 存在しない、または他人の Capture。
            CaptureNotRetryableError: 失敗状態ではない Capture。
        """
        retried = await self._repository.retry_failed_capture(
            user_id, capture_id=capture_id, outbox_id=uuid7()
        )
        if retried is not None:
            return retried

        current = await self._repository.get_by_id(user_id, capture_id=capture_id)
        if current is None:
            raise CaptureNotFoundError(capture_id)

        raise CaptureNotRetryableError()

    async def process_capture(self, capture_id: UUID, processing_generation: int) -> None:
        """Capture を分類し、ルート、確認質問、シナリオ、embedding を保存する。

        ジョブの重複実行や再試行で二重に処理しないよう、世代が違う場合と、
        完了済みか失敗済みの場合は何もせずに戻る。pending から processing への
        更新に成功した 1 回だけが処理を続ける。タイムゾーンはリマインダー
        ルートのシナリオにしか要らないので、そのときだけ取得する。
        embedding は、同じ本文のものが保存済みなら作り直さない。

        Args:
            capture_id: 処理する Capture。
            processing_generation: ジョブが想定する処理の世代。
        """
        capture = await self._repository.get_by_capture_id(capture_id)
        if (
            capture is None
            or capture.processing_generation != processing_generation
            or capture.status in {CAPTURE_STATUS_COMPLETED, CAPTURE_STATUS_FAILED}
        ):
            return

        # statusをprocessingに更新
        is_started = await self._repository.update_processing_status(
            capture_id=capture_id,
            processing_generation=capture.processing_generation,
            expected_status=CAPTURE_STATUS_PENDING,
            status=CAPTURE_STATUS_PROCESSING,
        )
        if not is_started:
            return

        classification = await self._classifier.classify_capture(
            capture.raw_text,
            question_version=CAPTURE_QUESTION_VERSION,
        )
        normalized_classification = normalize_classification(classification)
        urgency_score = normalize_urgency_score(normalized_classification.urgency_score)
        route = decide_capture_route(
            category=normalized_classification.category,
            confidence=normalized_classification.confidence,
        )
        clarification_text: str | None = None
        if route == CAPTURE_ROUTE_CLARIFY:
            generated = await self._generator.generate_clarification(
                capture.raw_text,
                category=normalized_classification.category,
            )
            clarification_text = normalize_clarification_text(generated)
        timezone = (
            await self._profiles.get_timezone(capture.user_id)
            if route == CAPTURE_ROUTE_REMINDER
            else "UTC"
        )

        scenario = propose_capture_scenario(
            route=route, raw_text=capture.raw_text, now=self._clock(), timezone=timezone
        )

        embedding: Embedding | None = None
        if capture.raw_text.strip() != "":
            # hashの照合はcomplete_capture_classificationと同じraw_textで行う
            has_embedding = await self._repository.has_same_content_embedding(
                capture.user_id, capture_id=capture_id, text=capture.raw_text
            )
            if not has_embedding:
                embedding = await self._embedder.embed_text(capture.raw_text)

        await self._repository.complete_capture_classification(
            capture_id=capture_id,
            processing_generation=capture.processing_generation,
            category=normalized_classification.category,
            route=route,
            urgency="normal",
            urgency_score=urgency_score,
            confidence=normalized_classification.confidence,
            policy_version=CAPTURE_ROUTE_POLICY_VERSION,
            question_version=normalized_classification.question_version,
            clarification_text=clarification_text,
            scenario=scenario,
            embedding=embedding,
        )

    async def mark_processing_failed(self, capture_id: UUID, processing_generation: int) -> None:
        """Capture の処理状態を failed にする。

        世代と状態が一致するときだけ更新する。古いジョブの失敗が、
        再試行後の処理を上書きしないようにするため。

        Args:
            capture_id: 失敗扱いにする Capture。
            processing_generation: 失敗したジョブの処理の世代。
        """
        await self._repository.update_processing_status(
            capture_id=capture_id,
            processing_generation=processing_generation,
            expected_status=CAPTURE_STATUS_PENDING,
            status=CAPTURE_STATUS_FAILED,
        )

    async def accept_capture_scenario(self, user_id: UUID, capture_id: UUID) -> Capture:
        """Capture に提案されたシナリオを承認する。

        承認できなかったときだけ読み直し、Capture かシナリオが無いのか、
        承認できない状態なのかを区別する。

        Args:
            user_id: 所有者。
            capture_id: シナリオを承認する Capture。

        Returns:
            承認後の Capture。

        Raises:
            CaptureNotFoundError: Capture かシナリオが存在しない、または他人のもの。
            ScenarioNotAcceptableError: 承認できない状態のシナリオ。
        """
        is_accepted = await self._repository.accept_capture_scenario(user_id, capture_id=capture_id)
        if is_accepted:
            capture = await self._repository.get_by_id(user_id, capture_id=capture_id)
            if capture is None:
                raise CaptureNotFoundError(capture_id)
            return capture

        current = await self._repository.get_by_id(user_id, capture_id=capture_id)
        scenario = None
        if current is not None:
            scenario = await self._repository.get_capture_scenario(user_id, capture_id=capture_id)
        if current is None or scenario is None:
            raise CaptureNotFoundError(capture_id)

        raise ScenarioNotAcceptableError()

    async def set_capture_scenario_done(
        self, user_id: UUID, capture_id: UUID, *, done: bool
    ) -> Capture:
        """所有者の Capture のシナリオを、完了にする、または未完了に戻す。

        同じ操作を繰り返しても結果は変わらない。完了にしたあとに、もう一度完了に
        しても、最初の完了時刻が残る。シナリオの確認状態は見ない。更新したあと、
        シナリオを含む最新の Capture を読み直して返す。

        Args:
            user_id: 所有者。
            capture_id: Capture の id。
            done: True なら完了にする。False なら未完了に戻す。

        Returns:
            更新後の Capture。シナリオを含む。

        Raises:
            CaptureNotFoundError: Capture が無い、別ユーザーの Capture、
                またはシナリオが無い。存在を隠すため、理由は区別しない。
        """

        is_updated = await self._repository.set_scenario_done(
            user_id, capture_id=capture_id, done=done
        )
        if not is_updated:
            raise CaptureNotFoundError(capture_id)

        capture = await self._repository.get_by_id(user_id, capture_id=capture_id)
        if capture is None:
            raise CaptureNotFoundError(capture_id)
        return capture

    def _replay_or_conflict(
        self, existing: Capture | None, request_hash: str
    ) -> CreateCaptureResult | None:
        """既存の Capture があれば、再送として返すか、衝突として例外にする。

        Args:
            existing: 同じ冪等キーで保存済みの Capture。無ければ None。
            request_hash: 今回の本文のハッシュ。

        Returns:
            再送なら created が False の結果。既存が無ければ None。

        Raises:
            IdempotencyKeyConflictError: 同じキーで本文のハッシュが違う。
        """
        if existing is None:
            return None
        if existing.request_hash == request_hash:
            return CreateCaptureResult(capture=existing, created=False)
        raise IdempotencyKeyConflictError()

    def _normalize_raw_text(self, raw_text: str) -> str:
        """本文の前後の空白を除き、長さを検証する。

        空白だけの本文を空として扱うため、長さは除いた後で数える。

        Args:
            raw_text: 入力された本文。

        Returns:
            前後の空白を除いた本文。

        Raises:
            CaptureTextInvalidError: 除いた後が空、または上限を超える。
        """
        stripped_raw_text = raw_text.strip()
        if len(stripped_raw_text) == 0 or len(stripped_raw_text) > _MAX_CAPTURE_LENGTH:
            raise CaptureTextInvalidError()
        return stripped_raw_text

    def _decode_cursor(self, cursor: str) -> tuple[datetime, UUID]:
        """一覧のカーソルを、作成日時と Capture ID に戻す。

        クライアントが任意の文字列を送れるため、形式の誤りは全て
        MalformedCursorError にそろえる。タイムゾーンの無い日時は、
        比較の基準がずれるので拒否する。

        Args:
            cursor: _encode_cursor が作った文字列。

        Returns:
            カーソルが指す Capture の作成日時と ID。

        Raises:
            MalformedCursorError: 復号できない、または必要な値が無い。
        """
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            raw = urlsafe_b64decode(padded)
            payload = json.loads(raw)
            created_at = datetime.fromisoformat(str(payload["c"]).replace("Z", "+00:00"))
            capture_id = UUID(str(payload["i"]))
        except KeyError, TypeError, ValueError, json.JSONDecodeError:
            raise MalformedCursorError() from None

        if created_at.tzinfo is None:
            raise MalformedCursorError() from None
        return created_at, capture_id

    def _encode_cursor(self, created_at: datetime, capture_id: UUID) -> str:
        """作成日時と Capture ID を、一覧の次ページ用カーソルにする。

        URL に載せやすいよう、JSON を padding 無しの URL-safe base64 にする。
        日時は UTC にそろえ、同じ時刻なら同じカーソルになるようにする。

        Args:
            created_at: 現在のページ末尾の Capture の作成日時。
            capture_id: 現在のページ末尾の Capture の ID。

        Returns:
            _decode_cursor で戻せる文字列。
        """
        payload = {
            "c": created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
            "i": str(capture_id),
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
