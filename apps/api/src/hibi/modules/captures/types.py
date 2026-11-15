from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

CAPTURE_AGGREGATE_TYPE = "capture"
CAPTURE_PROCESSING_REQUESTED = "capture.processing_requested"

CAPTURE_STATUS_PENDING = "pending"
CAPTURE_STATUS_PROCESSING = "processing"
CAPTURE_STATUS_COMPLETED = "completed"
CAPTURE_STATUS_FAILED = "failed"

OUTBOX_STATUS_PENDING = "pending"
OUTBOX_STATUS_PUBLISHED = "published"

CAPTURE_PROCESSING_MAX_ATTEMPTS = 3

CAPTURE_SEARCH_MODE_KEYWORD = "keyword"
CAPTURE_SEARCH_MODE_SEMANTIC = "semantic"
CAPTURE_SEARCH_LIMIT = 20

TODAY_MAX_LIMIT = 20
TODAY_DEFAULT_LIMIT = 5


CaptureSearchMode = Literal["keyword", "semantic"]


@dataclass(frozen=True, slots=True)
class Capture:
    """Capture 1 件を表すドメインの型。DB の行と、API の応答の間に置く。

    Attributes:
        id: Capture の id。
        user_id: 所有者。
        raw_text: 生入力。trim 済み。
        status: pending、processing、completed、failed のいずれか。
        idempotency_key: 作成時の冪等キー。API には出さない。
        request_hash: 作成時の本文から求めた hash。API には出さない。
        processing_generation: 処理の世代。retry のたびに 1 増える。
        category: 分類の結果。完了前は None。
        route: 処理の振り分け先。確信度が足りないときは clarify。完了前は None。
        urgency: 緊急度の label。完了前は None。
        confidence: 分類の確信度。完了前は None。
        policy_version: route の policy の版。完了前は None。
        question_version: 分類の質問の版。完了前は None。
        processed_at: 分類を保存した時刻。完了前は None。
        clarification_text: 聞き返し文。route が clarify のときだけ。
        created_at: 作成時刻。
        updated_at: 更新時刻。
        scenario: 付随するシナリオ。読み出しのときだけ付き、作成、更新、
            処理の完了の戻り値には付かない。シナリオが無い Capture も None。
    """

    id: UUID
    user_id: UUID
    raw_text: str
    status: str
    idempotency_key: str
    request_hash: str
    processing_generation: int
    category: str | None
    route: str | None
    urgency: str | None
    confidence: Decimal | None
    policy_version: str | None
    question_version: str | None
    processed_at: datetime | None
    clarification_text: str | None
    created_at: datetime
    updated_at: datetime
    scenario: CaptureScenario | None = None


@dataclass(frozen=True, slots=True)
class CreateCaptureCommand:
    """Capture の作成の入力。

    Attributes:
        user_id: 検証済みの所有者。
        raw_text: 未 trim の原文。service が trim と長さの検証を行う。
        idempotency_key: Idempotency-Key ヘッダーの値。無ければ None。
    """

    user_id: UUID
    raw_text: str
    idempotency_key: str | None


@dataclass(frozen=True, slots=True)
class CreateCaptureResult:
    """Capture の作成の結果。

    Attributes:
        capture: 作成した Capture。再送のときは、既に保存されている Capture。
        created: 初回なら True。router が 202 と 200 を分ける。
    """

    capture: Capture
    created: bool


@dataclass(frozen=True, slots=True)
class UpdateCaptureCommand:
    """Capture の本文の更新の入力。

    Attributes:
        user_id: 検証済みの所有者。
        capture_id: 更新する Capture の id。
        raw_text: 未 trim の新しい本文。service が trim と長さの検証を行う。
    """

    user_id: UUID
    capture_id: UUID
    raw_text: str


@dataclass(frozen=True, slots=True)
class ListCapturesQuery:
    """Capture の一覧の入力。

    Attributes:
        user_id: 検証済みの所有者。
        limit: 1 ページの件数。None なら 20。service が 1 以上 50 以下に収める。
        cursor: 前のページが返した、中身を見ない文字列。None なら先頭のページ。
    """

    user_id: UUID
    limit: int | None
    cursor: str | None


@dataclass(frozen=True, slots=True)
class SearchCapturesQuery:
    """Capture検索の入力。

    Attributes:
        user_id: 検証済みの所有者。検索はこのユーザーの行だけを対象にする。
        q: 検索語。router が1〜200文字で検証済み。
        mode: CAPTURE_SEARCH_MODE_KEYWORD か CAPTURE_SEARCH_MODE_SEMANTIC。
    """

    user_id: UUID
    q: str
    mode: str


@dataclass(frozen=True, slots=True)
class CapturePage:
    """Capture の一覧の 1 ページ。

    Attributes:
        items: 新しい順の Capture。
        next_cursor: 続きを読むための cursor。続きが無ければ None。
        has_next_page: 続きがあるか。
    """

    items: list[Capture]
    next_cursor: str | None
    has_next_page: bool


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """配送待ちの outbox 1 件のうち、arq に投入するのに必要な項目。

    Attributes:
        id: outbox の id。job の重複防止の id に使う。
        aggregate_id: 処理する Capture の id。
        processing_generation: 依頼した処理の世代。
    """

    id: UUID
    aggregate_id: UUID
    aggregate_type: str
    processing_generation: int


@dataclass(frozen=True, slots=True)
class CaptureScenario:
    """Capture に付く、シナリオ 1 件。保存済みの行を表す。

    Worker が作る前の提案は `ScenarioProposal` で、こちらは読み出した結果。

    Attributes:
        route: shopping、reminder、expense のいずれか。
        status: proposed か accepted。ユーザーが確認したかを表す。
        title: 画面に出す題。
        amount: 円の整数。支出で金額が取れたときだけ。
        remind_text: 予定の時刻表現。reminder で取り出せたときだけ。
        policy_version: シナリオを作った policy の版。
        due_at: 期限。UTC の aware な datetime。解釈できなければ None。
        done_at: ユーザーが完了にした時刻。未完了なら None。
    """

    route: str
    status: str
    title: str
    amount: int | None
    remind_text: str | None
    policy_version: str
    due_at: datetime | None = None
    done_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TodayCapturesQuery:
    """Today の一覧の入力。

    Attributes:
        user_id: 検証済みの所有者。
        limit: 返す最大件数。router が 1 以上 20 以下で検証済み。
    """

    user_id: UUID
    limit: int
