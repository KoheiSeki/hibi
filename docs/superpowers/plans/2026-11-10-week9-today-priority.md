# Week 9 Today 優先度 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 所有者の未完了シナリオを、保存済みの緊急度と期限から優先度順に最大 N 件返す `GET /api/v1/captures/today` と、`/captures/today` 画面を作る。

**Architecture:** 期限の抽出と優先度は、DB も時計も持たない純粋関数(`due.py`、`today.py`)に置き、現在時刻とタイムゾーンは引数で渡す。Worker は `urgency_score` と `due_at` を完了更新と同じ UPDATE で保存する。Today は読み取り時に優先度を計算し、保存済みの `list_captures_by_ids` で Capture を組み立てる。完了は `capture_scenarios.done_at` で表す。

**Tech Stack:** FastAPI + SQLAlchemy 2 async, Python 3.14 (`zoneinfo`, `Decimal`), Supabase migration, Next.js 16 / React 19, vitest。

**Spec:** `docs/architecture/27-week9-today-priority.md`

## Global Constraints

- 優先度の補正は、期限超過 `+0.6`、今日の終わりまでの期限 `+0.4`。`urgency_score` が null のときの基準は `0.5`。計算は `Decimal`
- 今日の終わりは、ユーザーの暦日の翌日 0 時。ちょうど翌日 0 時の期限は対象外
- 並びは優先度の降順、`due_at` の昇順(null は最後)、`created_at` の昇順、`capture_id` の昇順
- `limit` は 1 以上 20 以下、未指定は 5。範囲外は 422
- 期限の規則: 日は `今日`・`明日`・`明後日`、時は `午前`/`午後` 任意の `N時`(`午後` で N が 12 未満なら +12、N は 0 以上 23 以下)、分は `M分`(0 以上 59 以下)か `半`、時が無ければ 23 時 59 分。日も時も無ければ null。不正な timezone 名は `UTC`
- `profiles.timezone` の既定は `Asia/Tokyo`。既存の `UTC` の行も更新する(承認済み 2026-11-10: ローカルの開発データを書き換える。Task 3 の migration で実施する)
- 完了と取り消しは、どちらも 200 を返し、繰り返しても 200。`done_at` は最初の時刻を残す。所有者でない、またはシナリオが無いときは 404
- 新しい path は `/{capture_id}` より前に登録する。`Query` の既定値は `Annotated[int, Query(ge=1, le=20)] = 5` の形(ruff B008)
- docstring は日本語の Google style。全角括弧 `(` `)` は使わない(RUF002/RUF003)
- web は、色のトークン Field `#EEF3EF` / Ink `#15201A` / Moss `#1E6B43` / Leaf `#F7FBF8` / Dusk `#5A6A62` / Thread `#D5E3D9` だけを使う。バッジと緊急度の色分けは足さない
- 検証は `uv run --project apps/api pytest apps/api/tests -m 'not integration'`、`ruff check`、`ruff format --check`、`ty check apps/api/src`、`corepack pnpm typecheck|lint|test|build`。`format:check` は設定が無く既知の失敗のため使わない

## Review Focus

1. `午後 3 時` が 03:00 ではなく 15:00 になる → Task 1
2. 夏時間の日(`America/New_York` の 2026-03-08 は 23 時間、2026-11-01 は 25 時間)でも今日の終わりが翌日 0 時になる → Task 2
3. 昨日までに超過した行が、同じ緊急度の期限なしの行や今日期限の行より上に出る → Task 2
4. 期限がちょうど翌日 0 時の行は出ず、1 分前の行は出る → Task 2
5. 別ユーザーの行、完了済み、`pending` / `processing` / `failed`、シナリオ無しの行は出ない → Task 4 の integration
6. プロフィールの timezone 名が不正でも 500 にならず `UTC` で動く → Task 1, Task 4
7. 完了 API を繰り返しても 200 で `done_at` が変わらず、別ユーザーは 404 → Task 4

## File Structure

| ファイル | 責務 |
| --- | --- |
| `apps/api/src/hibi/core/timezone.py` (新規) | `zone_for`。不正な IANA 名を `UTC` に倒す。`due.py` と `today.py` が共有する |
| `apps/api/src/hibi/modules/captures/due.py` (新規) | `extract_remind_text`, `parse_due_at`。純粋関数 |
| `apps/api/src/hibi/modules/captures/today.py` (新規) | 優先度、今日の終わり、並び。純粋関数 |
| `apps/api/src/hibi/modules/captures/policies.py` (変更) | `ScenarioProposal.due_at`、`propose_capture_scenario` の引数、`normalize_urgency_score` |
| `apps/api/src/hibi/modules/captures/service.py` / `repository.py` / `router.py` / `types.py` / `schemas.py` / `models.py` (変更) | 保存、Today、完了 API |
| `supabase/migrations/20261110000000_today_priority.sql` (新規) | 列の追加と timezone の既定 |
| `apps/web/src/lib/api/capture.ts`, `apps/web/src/features/capture/*` (変更・新規) | Today 画面と完了操作 |

---

### Task 1: 期限の抽出と `due_at`(純粋関数)

**Files:**

- Create: `apps/api/src/hibi/modules/captures/due.py`
- Test: `apps/api/tests/test_capture_due.py`

**Interfaces:**

- Produces:
  - `zone_for(timezone: str) -> ZoneInfo` — 不正な名前は `UTC`(Task 1 では `due.py` に置いた。Task 1b で `hibi.core.timezone` へ移す)
  - `extract_remind_text(raw_text: str) -> str | None` — 本文から日・時の表現を取り出す。無ければ None
  - `parse_due_at(remind_text: str, *, now: datetime, timezone: str) -> datetime | None` — UTC の aware な `datetime`。`now` は aware

- [x] **Step 1: Write the failing tests** in `tests/test_capture_due.py`

```python
from datetime import UTC, datetime

import pytest

from hibi.modules.captures.due import extract_remind_text, parse_due_at

# 2026-11-10 15:00 JST
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
JST = "Asia/Tokyo"


@pytest.mark.parametrize(
    ("raw_text", "expected"),
    [
        ("明日の 9 時に起こして", "明日の 9 時"),
        ("午後3時に会議", "午後3時"),
        ("明日までに提出", "明日"),
        ("今日の 9 時 30 分に電話", "今日の 9 時 30 分"),
        ("牛乳を買う", None),
        ("3時間かかる", None),
    ],
)
def test_extract_remind_text(raw_text: str, expected: str | None) -> None:
    assert extract_remind_text(raw_text) == expected


@pytest.mark.parametrize(
    ("remind_text", "expected"),
    [
        ("明日の 9 時", datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),
        ("午後3時", datetime(2026, 11, 10, 6, 0, tzinfo=UTC)),
        ("今日の 9 時 30 分", datetime(2026, 11, 10, 0, 30, tzinfo=UTC)),
        ("明日の 9 時半", datetime(2026, 11, 11, 0, 30, tzinfo=UTC)),
        ("明後日の 9 時", datetime(2026, 11, 12, 0, 0, tzinfo=UTC)),
        ("明日", datetime(2026, 11, 11, 14, 59, tzinfo=UTC)),
    ],
)
def test_parse_due_at_in_the_user_timezone(remind_text: str, expected: datetime) -> None:
    assert parse_due_at(remind_text, now=NOW, timezone=JST) == expected


def test_parse_due_at_uses_the_local_date_of_now() -> None:
    # UTC では 11/10 20:00 だが JST では 11/11 05:00
    now = datetime(2026, 11, 10, 20, 0, tzinfo=UTC)
    assert parse_due_at("今日の 9 時", now=now, timezone=JST) == datetime(
        2026, 11, 11, 0, 0, tzinfo=UTC
    )


@pytest.mark.parametrize("remind_text", ["25 時", "9 時 60 分", "ランチ"])
def test_parse_due_at_returns_none_for_invalid_or_missing_expressions(remind_text: str) -> None:
    assert parse_due_at(remind_text, now=NOW, timezone=JST) is None


def test_parse_due_at_treats_an_unknown_timezone_as_utc() -> None:
    assert parse_due_at("明日の 9 時", now=NOW, timezone="Not/AZone") == datetime(
        2026, 11, 11, 9, 0, tzinfo=UTC
    )
```

- [x] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_due.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.modules.captures.due`)

- [x] **Step 3: Implement** `extract_remind_text` **and** `parse_due_at` in `due.py`

正規表現 1 本で日・午前午後・時・分/半を捕まえる(名前付きグループ `day`・`meridiem`・`hour`・`minute`・`half` と、日だけの系統の `day_only`。時の直後が `間` の `3時間` は `(?!間)` で時刻として扱わない)。`extract_remind_text` は一致した部分文字列を前後の空白なしで返す。`parse_due_at` は `ZoneInfo(timezone)`(失敗したら `UTC`)で `now` の暦日を求め、日の加算は暦日で行い、時刻を足して UTC に直す。範囲外の時・分は None。`ZoneInfo` の失敗を `UTC` に倒す公開関数 `zone_for(timezone: str) -> ZoneInfo` を `due.py` に置き、Task 2 の `today.py` も使う。

  3 つの関数に、日本語の Google style の docstring を付ける(全角括弧は使わない)。

- [x] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_due.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add apps/api/src/hibi/modules/captures/due.py apps/api/tests/test_capture_due.py
git commit -m "feat(captures): extract reminder deadlines in the user timezone"
```

---

### Task 1b: `zone_for` を `core/timezone.py` へ切り出す

`due.py` と `today.py` の両方が使うため、Task 2 の前に共有の場所へ移す。`today.py` が期限の抽出(`due.py`)に依存する形を避ける。動作は変えない。

**Files:**

- Create: `apps/api/src/hibi/core/timezone.py`
- Modify: `apps/api/src/hibi/modules/captures/due.py`(`zone_for` を削除し、import に変える)
- Test: `apps/api/tests/test_timezone.py`(新規)、`apps/api/tests/test_capture_due.py`(不正な timezone 名のケースを移す)

**Interfaces:**

- Produces: `hibi.core.timezone.zone_for(timezone: str) -> ZoneInfo` — 存在しない名前や不正な名前は `UTC`。Task 2 の `today.py` と Task 3 以降が使う

- [ ] **Step 1: Write the failing test** in `tests/test_timezone.py`

```python
from zoneinfo import ZoneInfo

import pytest

from hibi.core.timezone import zone_for


def test_zone_for_returns_the_named_zone() -> None:
    assert zone_for("Asia/Tokyo") == ZoneInfo("Asia/Tokyo")


@pytest.mark.parametrize("name", ["", "Asia", "Asia/", "../etc/passwd", "Not/AZone"])
def test_zone_for_falls_back_to_utc_for_unknown_or_invalid_names(name: str) -> None:
    assert zone_for(name) == ZoneInfo("UTC")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_timezone.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.core.timezone`)

- [ ] **Step 3: Move `zone_for`**

`zone_for` を、`due.py` の実装(`ZoneInfoNotFoundError` と `ValueError` を捕まえて `UTC`)と docstring ごと `core/timezone.py` へ移す。`due.py` は `from hibi.core.timezone import zone_for` に変え、自分の定義を消す。`test_capture_due.py` の不正な timezone 名のケースは、`test_timezone.py` と重なるので 1 件だけ残す。

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_timezone.py apps/api/tests/test_capture_due.py -v` と `ruff check`、`ty check apps/api/src`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/hibi/core/timezone.py apps/api/src/hibi/modules/captures/due.py apps/api/tests/test_timezone.py apps/api/tests/test_capture_due.py
git commit -m "refactor(core): share zone_for between the due and today modules"
```

---

### Task 2: 優先度と並び(純粋関数)

**Files:**

- Create: `apps/api/src/hibi/modules/captures/today.py`
- Test: `apps/api/tests/test_capture_today.py`

**Interfaces:**

- Consumes: Task 1b の `hibi.core.timezone.zone_for(timezone: str) -> ZoneInfo`
- Produces:
  - `TODAY_DEFAULT_LIMIT = 5`, `TODAY_MAX_LIMIT = 20`
  - `@dataclass(frozen=True, slots=True) class TodayCandidate: capture_id: UUID; urgency_score: Decimal | None; due_at: datetime | None; created_at: datetime`
  - `local_day_end(now: datetime, *, timezone: str) -> datetime` — 翌日 0 時の UTC
  - `calculate_today_priority(candidate: TodayCandidate, *, now: datetime) -> Decimal`
  - `rank_today(candidates: Sequence[TodayCandidate], *, now: datetime, timezone: str, limit: int) -> list[UUID]`

- [x] **Step 1: Write the failing tests** in `tests/test_capture_today.py`

```python
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from hibi.modules.captures.today import (
    TodayCandidate,
    calculate_today_priority,
    local_day_end,
    rank_today,
)

JST = "Asia/Tokyo"
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)  # 15:00 JST
CREATED = datetime(2026, 11, 1, tzinfo=UTC)


def _id(n: int) -> UUID:
    return UUID(int=n)


def _candidate(n: int, *, urgency: str | None = "0.50", due: datetime | None = None,
               created: datetime = CREATED) -> TodayCandidate:
    return TodayCandidate(
        capture_id=_id(n),
        urgency_score=None if urgency is None else Decimal(urgency),
        due_at=due,
        created_at=created,
    )


@pytest.mark.parametrize(
    ("now", "timezone", "expected"),
    [
        (NOW, JST, datetime(2026, 11, 10, 15, 0, tzinfo=UTC)),
        (datetime(2026, 3, 8, 12, 0, tzinfo=UTC), "America/New_York",
         datetime(2026, 3, 9, 4, 0, tzinfo=UTC)),  # 23 時間の日
        (datetime(2026, 11, 1, 12, 0, tzinfo=UTC), "America/New_York",
         datetime(2026, 11, 2, 5, 0, tzinfo=UTC)),  # 25 時間の日
        (NOW, "Not/AZone", datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),
    ],
)
def test_local_day_end(now: datetime, timezone: str, expected: datetime) -> None:
    assert local_day_end(now, timezone=timezone) == expected


def test_priority_adds_the_deadline_bonus() -> None:
    overdue = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    later_today = datetime(2026, 11, 10, 11, 0, tzinfo=UTC)
    assert calculate_today_priority(_candidate(1), now=NOW) == Decimal("0.50")
    assert calculate_today_priority(_candidate(1, due=overdue), now=NOW) == Decimal("1.10")
    assert calculate_today_priority(_candidate(1, due=later_today), now=NOW) == Decimal("0.90")
    assert calculate_today_priority(_candidate(1, urgency=None), now=NOW) == Decimal("0.50")


def test_rank_orders_overdue_then_today_then_no_deadline_and_drops_later_days() -> None:
    candidates = [
        _candidate(1),  # 期限なし 0.5
        _candidate(2, due=datetime(2026, 11, 10, 0, 0, tzinfo=UTC)),  # 超過 1.1
        _candidate(3, due=datetime(2026, 11, 10, 11, 0, tzinfo=UTC)),  # 今日 0.9
        _candidate(4, due=datetime(2026, 11, 11, 0, 0, tzinfo=UTC)),  # 明日 対象外
        _candidate(5, due=datetime(2026, 11, 10, 15, 0, tzinfo=UTC)),  # ちょうど翌日 0 時 対象外
        _candidate(6, due=datetime(2026, 11, 10, 14, 59, tzinfo=UTC)),  # 1 分前 対象
    ]
    assert rank_today(candidates, now=NOW, timezone=JST, limit=10) == [
        _id(2), _id(3), _id(6), _id(1),
    ]


def test_high_urgency_without_a_deadline_beats_low_urgency_due_today() -> None:
    high = _candidate(1, urgency="0.95")
    low = _candidate(2, urgency="0.10", due=datetime(2026, 11, 10, 11, 0, tzinfo=UTC))
    assert rank_today([low, high], now=NOW, timezone=JST, limit=5) == [_id(1), _id(2)]


def test_ties_are_broken_by_due_created_then_id_regardless_of_input_order() -> None:
    older = datetime(2026, 10, 1, tzinfo=UTC)
    a = _candidate(3, created=older)
    b = _candidate(2, created=CREATED)
    c = _candidate(1, created=CREATED)
    expected = [_id(3), _id(1), _id(2)]
    assert rank_today([a, b, c], now=NOW, timezone=JST, limit=5) == expected
    assert rank_today([c, b, a], now=NOW, timezone=JST, limit=5) == expected


def test_rank_applies_the_limit() -> None:
    candidates = [_candidate(n) for n in range(1, 8)]
    assert len(rank_today(candidates, now=NOW, timezone=JST, limit=3)) == 3
```

- [x] **Step 2: Run to verify it fails**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_today.py -v`
Expected: FAIL(`ModuleNotFoundError: hibi.modules.captures.today`)

- [ ] **Step 3: Implement** `today.py`

`local_day_end` は `now.astimezone(zone)` の暦日の翌日を `datetime.combine(next_date, time.min, tzinfo=zone)` で作り UTC へ。暦日の加算で行い、24 時間を足さない(夏時間)。`calculate_today_priority` は基準(null は `Decimal("0.5")`)に、期限なし 0、`due_at < now` で `Decimal("0.6")`、それ以外は `Decimal("0.4")` を足す。`rank_today` は `due_at is None or due_at < local_day_end(...)` の行だけを残し、ソートキー `(-priority, due_at is None, due_at, created_at, capture_id)` で並べて `limit` 件の id を返す。定数のボーナス値は `today.py` の module 定数にする。docstring には Spec の「優先度」の表を要約する。

  `TodayCandidate`・`local_day_end`・`calculate_today_priority`・`rank_today` に、日本語の Google style の docstring を付ける(全角括弧は使わない)。`TodayCandidate` は `Attributes:` に 4 フィールドを書く。`local_day_end` は「翌日 0 時、暦日で数えるので夏時間の日は 23 時間や 25 時間、ちょうどの期限は明日の扱い」。`calculate_today_priority` は「基準と補正の値、今日の終わりを過ぎた期限の除外は `rank_today` が行う」。`rank_today` は「対象外の条件、並び順、入力の順序に依存しないこと」と `Args` / `Returns`。`local_day_end` に時刻の引数は足さない(日の終わりは翌日 0 時に固定で、`now` が暦日を決める)。

- [ ] **Step 4: Run to verify it passes**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_today.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/hibi/modules/captures/today.py apps/api/tests/test_capture_today.py
git commit -m "feat(captures): rank today candidates by urgency and deadline"
```

---

### Task 3: `urgency_score` と `due_at` を保存する

**Files:**

- Create: `supabase/migrations/20261110000000_today_priority.sql`
- Modify: `apps/api/src/hibi/modules/captures/models.py`, `policies.py`, `repository.py`, `service.py`, `types.py`
- Test: `apps/api/tests/test_capture_scenario_policy.py`, `apps/api/tests/test_capture_route_policy.py`, `apps/api/tests/test_process_capture_service.py`, `apps/api/tests/integration/test_capture_repository.py`

**Interfaces:**

- Consumes: Task 1 の `extract_remind_text`, `parse_due_at`
- Produces:
  - `normalize_urgency_score(score: float) -> Decimal | None` — 0 以上 1 以下なら小数 2 桁に丸めた `Decimal`、範囲外は None
  - `ScenarioProposal` に `due_at: datetime | None = None`
  - `propose_capture_scenario(*, route: str, raw_text: str, now: datetime, timezone: str) -> ScenarioProposal | None`
  - `CaptureRepository.get_user_timezone(user_id: UUID) -> str` — プロフィールが無いとき `"UTC"`
  - `CaptureRepository.complete_capture_classification(..., urgency_score: Decimal | None)` — 新しい必須の keyword 引数
  - `CaptureScenario` に `due_at: datetime | None = None`, `done_at: datetime | None = None`
  - `CaptureService.__init__(..., clock: Callable[[], datetime] = _utc_now)` — 末尾の keyword 引数。既存の呼び出しは壊れない

- [ ] **Step 1: Write the failing tests**

`test_capture_route_policy.py` に追加する。

```python
@pytest.mark.parametrize(
    ("score", "expected"),
    [(0.0, Decimal("0.00")), (0.5, Decimal("0.50")), (0.666, Decimal("0.67")),
     (1.0, Decimal("1.00")), (-0.1, None), (1.1, None)],
)
def test_normalize_urgency_score(score: float, expected: Decimal | None) -> None:
    assert normalize_urgency_score(score) == expected
```

`test_capture_scenario_policy.py` の既存の `propose_capture_scenario` 呼び出しに `now=NOW, timezone="Asia/Tokyo"` を足し、次を加える。

```python
def test_reminder_gets_remind_text_and_due_at() -> None:
    proposal = propose_capture_scenario(
        route="reminder", raw_text="明日の 9 時に起こして", now=NOW, timezone="Asia/Tokyo"
    )
    assert proposal is not None
    assert proposal.remind_text == "明日の 9 時"
    assert proposal.due_at == datetime(2026, 11, 11, 0, 0, tzinfo=UTC)

def test_reminder_without_an_expression_has_no_due_at() -> None:
    proposal = propose_capture_scenario(
        route="reminder", raw_text="薬を飲む", now=NOW, timezone="Asia/Tokyo"
    )
    assert proposal is not None and proposal.due_at is None and proposal.remind_text is None

def test_shopping_and_expense_never_get_a_due_at() -> None:
    proposal = propose_capture_scenario(
        route="shopping", raw_text="明日の 9 時に牛乳を買う", now=NOW, timezone="Asia/Tokyo"
    )
    assert proposal is not None and proposal.due_at is None
```

`test_process_capture_service.py` に追加する。既存の fake repository に `get_user_timezone` を足し(呼び出しを記録、既定 `"Asia/Tokyo"`)、service は `clock=lambda: NOW` で作る。

```python
async def test_reminder_saves_due_at_and_urgency_score() -> None:
    # raw_text="明日の 9 時に起こして"、fake classifier の route=reminder、urgency_score=0.5
    # complete_capture_classification の呼び出しに urgency_score == Decimal("0.50")
    # scenario.due_at == datetime(2026, 11, 11, 0, 0, tzinfo=UTC)

async def test_non_reminder_does_not_read_the_user_timezone() -> None:
    # raw_text="牛乳を買う" → get_user_timezone の呼び出し回数 0、scenario.due_at is None

async def test_out_of_range_urgency_score_is_saved_as_null() -> None:
    # classifier が urgency_score=1.5 → urgency_score is None で完了する
```

`tests/integration/test_capture_repository.py` に追加する(`integration`)。

```python
async def test_complete_classification_saves_urgency_score_and_due_at(...) -> None:
    # 完了後に CaptureModel.urgency_score == Decimal("0.50")、CaptureScenarioModel.due_at が一致

async def test_get_user_timezone_defaults_to_tokyo_and_falls_back_to_utc(...) -> None:
    # 新規プロフィールは "Asia/Tokyo"。存在しない user_id は "UTC"
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_route_policy.py apps/api/tests/test_capture_scenario_policy.py apps/api/tests/test_process_capture_service.py -v`
Expected: FAIL(`normalize_urgency_score` が無い、`propose_capture_scenario` の引数が合わない)

- [ ] **Step 3: Implement**

- migration `20261110000000_today_priority.sql`:
`alter table app.captures add column urgency_score numeric(3,2)` と `constraint ck_captures__urgency_score check (urgency_score is null or (urgency_score >= 0 and urgency_score <= 1))`。`alter table app.capture_scenarios add column due_at timestamptz, add column done_at timestamptz`。`alter table app.profiles alter column timezone set default 'Asia/Tokyo'` と `update app.profiles set timezone = 'Asia/Tokyo' where timezone = 'UTC'`(Global Constraints の承認済み事項)。
- `models.py` に 3 列、`types.py` の `CaptureScenario` に 2 列(既定 None)、`policies.py` の `normalize_urgency_score`、`ScenarioProposal.due_at`、`propose_capture_scenario` の新引数。reminder のとき `extract_remind_text(raw_text)`(dataset の完全一致は従来の値を優先)で `remind_text` を決め、`parse_due_at` で `due_at` を決める。
- `repository.py`: `get_user_timezone`(`app.profiles` を `user_id` で 1 行読む。最小の `ProfileModel(user_id, timezone)` を `models.py` に置く)。`complete_capture_classification` に `urgency_score` を足し、UPDATE の values とシナリオの INSERT に `urgency_score`、`due_at` を入れる。
- `service.py`: `process_capture` で `normalize_urgency_score(normalized_classification.urgency_score)` を求め、route が `reminder` のときだけ `get_user_timezone` を呼び、`self._clock()` と合わせて `propose_capture_scenario` に渡す。それ以外の route は timezone を読まず `"UTC"` を渡す。コンストラクタに `clock: Callable[[], datetime] = _utc_now` を足す。

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --project apps/api pytest apps/api/tests -m 'not integration' -q` と `supabase db reset` 後に `uv run --project apps/api pytest apps/api/tests/integration/test_capture_repository.py -m integration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations apps/api/src apps/api/tests
git commit -m "feat(captures): store urgency score and reminder deadlines"
```

---

### Task 4: Today API と完了 API

**Files:**

- Modify: `apps/api/src/hibi/modules/captures/types.py`, `repository.py`, `service.py`, `router.py`, `schemas.py`
- Test: `apps/api/tests/test_capture_today_service.py`(新規)、`apps/api/tests/test_capture_api.py`、`apps/api/tests/integration/test_capture_repository.py`

**Interfaces:**

- Consumes: Task 2 の `TodayCandidate`, `rank_today`, `TODAY_DEFAULT_LIMIT`, `TODAY_MAX_LIMIT`、Task 3 の `get_user_timezone`
- Produces:
  - `TodayCapturesQuery(user_id: UUID, limit: int)`(`types.py`)
  - `CaptureRepository.list_today_candidates(user_id: UUID) -> list[TodayCandidate]` — `completed` の Capture のうち、シナリオがあり `done_at is null` の行。時刻の絞り込みは SQL でしない
  - `CaptureRepository.set_scenario_done(user_id: UUID, *, capture_id: UUID, done: bool) -> bool` — 行が無ければ False。`done=True` は `done_at = coalesce(done_at, now())`
  - `CaptureService.list_today_captures(query: TodayCapturesQuery) -> list[Capture]`
  - `CaptureService.set_capture_scenario_done(user_id: UUID, capture_id: UUID, *, done: bool) -> Capture` — 無ければ `CaptureNotFoundError`
  - `ScenarioResponse` に `dueAt`, `doneAt`
  - `GET /api/v1/captures/today`(`operation_id="listTodayCaptures"`)、`POST` と `DELETE /api/v1/captures/{capture_id}/scenario/done`(`operation_id="markCaptureScenarioDone"` / `"unmarkCaptureScenarioDone"`)

- [ ] **Step 1: Write the failing tests**

`test_capture_today_service.py`(`FakeSearchRepository` と同じ形の fake repository を使う)。

```python
async def test_today_returns_captures_in_priority_order() -> None:
    # 候補 3 件(期限超過、今日、期限なし)を fake repository が返す
    # service を clock=lambda: NOW、timezone="Asia/Tokyo" で作る
    # list_today_captures の結果の id の並びが [超過, 今日, 期限なし]

async def test_today_drops_candidates_due_after_the_end_of_the_local_day() -> None: ...

async def test_today_returns_an_empty_list_without_candidates() -> None:
    # list_captures_by_ids を呼ばず [] を返す

async def test_today_reads_the_timezone_of_the_owner() -> None:
    # get_user_timezone が query.user_id で呼ばれ、不正な名前でも例外にならない

async def test_set_done_returns_the_capture_or_raises_not_found() -> None: ...
```

`test_capture_api.py` に追加する。

```python
def test_today_returns_the_envelope_and_passes_the_limit(...) -> None:
    # GET /api/v1/captures/today?limit=3 → 200、service に limit=3 が渡る
def test_today_default_limit_is_five(...) -> None: ...
@pytest.mark.parametrize("limit", ["0", "21", "abc"])
def test_today_rejects_an_invalid_limit(limit) -> None:  # 422
def test_today_requires_authentication() -> None:  # 401
def test_today_is_registered_before_the_capture_id_route(...) -> None:
    # /today が UUID として解釈されず 200 になる
def test_mark_done_and_unmark_done_return_200_and_404(...) -> None:
    # POST と DELETE が 200、service が CaptureNotFoundError なら 404
```

`tests/integration/test_capture_repository.py` に追加する。

```python
async def test_list_today_candidates_excludes_other_owners_done_and_unfinished(...) -> None:
    # 自分の completed + 未完了だけが返る。別ユーザー、done_at あり、pending/processing/failed、シナリオ無しは返らない
async def test_set_scenario_done_is_idempotent_and_keeps_the_first_time(...) -> None:
    # done=True を 2 回呼んでも done_at が変わらない。done=False で null に戻る。別ユーザーは False
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run --project apps/api pytest apps/api/tests/test_capture_today_service.py apps/api/tests/test_capture_api.py -v`
Expected: FAIL(`list_today_captures` が無い、`/api/v1/captures/today` が 404)

- [ ] **Step 3: Implement**

`list_today_candidates` は `CaptureModel` と `CaptureScenarioModel` の inner join で、`CaptureModel.user_id == user_id`、`status == completed`、`CaptureScenarioModel.done_at.is_(None)` を条件にする。`list_today_captures` は `get_user_timezone` と `self._clock()` を読み、`rank_today(..., limit=query.limit)` の id を `list_captures_by_ids` で Capture にして、ランキングの順に並べ直す(`search_captures` と同じ形)。`_to_scenario_response` に `due_at`、`done_at` を足す。`/today` ルートは `/search` と同じく `/{capture_id}` より前に置く。`limit` は `Annotated[int, Query(ge=1, le=TODAY_MAX_LIMIT)] = TODAY_DEFAULT_LIMIT` の形にする。docstring の `description` は OpenAPI に出るので、日本語で Spec の「優先度」を要約する。

- [ ] **Step 4: Run to verify they pass**

Run: `uv run --project apps/api pytest apps/api/tests -m 'not integration' -q`、`ruff check apps/api/src apps/api/tests scripts`、`ty check apps/api/src`、integration は `supabase db reset` 後に実行
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src apps/api/tests
git commit -m "feat(captures): list today captures and complete scenarios over HTTP"
```

---

### Task 5: OpenAPI と client の再生成

**Files:**

- Modify: `contracts/openapi.json`, `packages/api-client/src/generated/*`

**Interfaces:**

- Consumes: Task 4 の `operation_id`
- Produces: `listTodayCaptures`, `markCaptureScenarioDone`, `unmarkCaptureScenarioDone` と、`ScenarioResponse` の `dueAt` / `doneAt`

- [ ] **Step 1: Regenerate**

Run: `just openapi`
Expected: `packages/api-client/src/generated/sdk.gen.ts` に 3 つの関数が出る。`git diff --stat` が `contracts/openapi.json` と `generated/` だけ

- [ ] **Step 2: Typecheck**

Run: `corepack pnpm typecheck && corepack pnpm build`
Expected: PASS。`next build` が書き換える `apps/web/next-env.d.ts` は `git checkout` で戻す

- [ ] **Step 3: Commit**

```bash
git add contracts/openapi.json packages/api-client
git commit -m "feat(contracts): regenerate the client for today and scenario completion"
```

---

### Task 6: Today 画面と完了操作

**Files:**

- Modify: `apps/web/src/lib/api/capture.ts`, `apps/web/src/features/capture/actions.ts`, `apps/web/src/features/capture/capture-action-state.ts`, `apps/web/src/app/captures/layout.tsx`, `apps/web/src/features/capture/capture-detail-editor.tsx`
- Create: `apps/web/src/app/captures/today/page.tsx`, `apps/web/src/features/capture/today-section.tsx`, `today-list.tsx`, `today-empty-state.tsx`
- Test: `apps/web/tests/capture-api.test.ts`, `capture-actions.test.ts`, `today-section.test.tsx`, `today-list.test.tsx`, `capture-detail-page.test.tsx`

**Interfaces:**

- Consumes: Task 5 の生成関数
- Produces:
  - `listTodayCapturesFromApi({ limit }?: { limit?: number }): Promise<ApiResult<CaptureResponse[]>>`
  - `markCaptureScenarioDoneFromApi(captureId: string)` / `unmarkCaptureScenarioDoneFromApi(captureId: string)`: `Promise<ApiResult<CaptureResponse>>`
  - `markScenarioDoneAction(captureId: string)` / `unmarkScenarioDoneAction(captureId: string)`: `Promise<ScenarioDoneActionState>`。成功時に `revalidatePath("/captures/today")` と `revalidatePath(`/captures/${captureId}`)`
  - `TodaySection(): Promise<ReactNode>`(server)、`TodayList({ items }: { items: readonly CaptureResponse[] })`(client)、`TodayEmptyState()`

- [ ] **Step 1: Write the failing tests**

`capture-api.test.ts` は、`@hibi/api-client` の mock に `listTodayCaptures`、`markCaptureScenarioDone`、`unmarkCaptureScenarioDone` を足す(足さないと既存テストまで落ちる)。次を加える。

```ts
it("passes limit and unwraps the data array for today", async () => {
	listTodayCapturesMock.mockResolvedValue({ data: { data: [capture] } });
	const result = await listTodayCapturesFromApi({ limit: 3 });
	expect(listTodayCapturesMock).toHaveBeenCalledWith({
		baseUrl: "https://api.hibi.example",
		auth: "access-token",
		query: { limit: 3 },
	});
	expect(result).toEqual({ ok: true, data: [capture] });
});
```

`today-section.test.tsx`(`capture-search-results-section.test.tsx` と同じ mock 形)。

```tsx
it("renders the scenario title and the due time", async () => {
	// data: [{ ..., scenario: { title: "起こして", route: "reminder", dueAt: "2026-11-11T00:00:00Z", ... } }]
	// html に "起こして", "09:00", 'href="/captures/capture-1"'
});
it("renders the empty state for an empty result", async () => { /* "今日やることはありません" */ });
it("redirects to /login when unauthenticated", async () => { /* redirectMock が "/login" */ });
it("renders the API error message for other failures", async () => { /* "通信に失敗しました" */ });
```

`today-list.test.tsx`: 各行に「完了にする」ボタンが出る。ボタンを押すと `markScenarioDoneAction` が `captureId` で呼ばれ、成功した行が消える。失敗時は `role="alert"` にメッセージを出し、行は残る。

`capture-actions.test.ts`: `markScenarioDoneAction` は空の id でエラーを返し、成功時に 2 つの path を revalidate する。

`capture-detail-page.test.tsx`: `scenario.doneAt` があるとき「完了済み」と「未完了に戻す」を出し、無いときは出さない。

- [ ] **Step 2: Run to verify they fail**

Run: `corepack pnpm --filter web exec vitest run`
Expected: FAIL(module not found)

- [ ] **Step 3: Implement**

`capture.ts` のラッパーは `getCaptureFromApi` と同じ形(`normalizeGeneratedResult`)。`TodaySection` は `CaptureListSection` と同じ構造で、行の本文は `scenario.title`、期限があれば `formatJstTime(dueAt)` を `<time>` で併記する。`CaptureList` の見た目(糸と節)を再利用するため、`CaptureListItemView` へ寄せる変換が足りなければ `map-capture-to-list-item.ts` に Today 用の変換を足す。`TodayList` は client component で、`useTransition` + `markScenarioDoneAction`、成功した行を state から外す。layout のヘッダーに「今日」のリンク(`/captures/today`)を足す。Today page は `await requireUser()` のあと `TodaySection` を `Suspense`(fallback は既存の `CaptureListSkeleton`)で包む。詳細の完了済み表示は `capture-detail-editor.tsx` の `visibleScenario` の下に足す。

- [ ] **Step 4: Run the web gate**

Run: `corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test && corepack pnpm build`
Expected: すべて PASS。`git checkout apps/web/next-env.d.ts`

- [ ] **Step 5: Manual check**(`docs/architecture/27-week9-today-priority.md` の手動確認)

`just dev-api`、`just dev-worker`、`just dev-web` を起動する。

1. `明日の 9 時に起こして` と `牛乳を買う` を記録し、`completed` になるのを待つ
2. `/captures/today` に両方が出る。`牛乳を買う`(期限なし)が上、翌日期限の `起こして` は出ない
3. 「完了にする」で行が消える
4. 詳細で「完了済み」「未完了に戻す」が出て、戻すと Today に戻る
5. 何も無いとき「今日やることはありません」が出る

- [ ] **Step 6: Commit**

```bash
git add apps/web
git commit -m "feat(web): show today captures and complete them"
```

---

### Task 7: 全ゲート

- [ ] **Step 1: Run every gate**

Run: `uv run --project apps/api ruff format --check apps/api/src apps/api/tests scripts`、`ruff check`、`ty check apps/api/src`、`uv run --project apps/api pytest apps/api/tests`、`corepack pnpm typecheck && corepack pnpm lint && corepack pnpm test && corepack pnpm build`
Expected: すべて GREEN(`format:check` は対象外)

- [ ] **Step 2: Commit the plan and spec**

```bash
git add docs/architecture/27-week9-today-priority.md docs/architecture/11-implementation-schedule.md docs/superpowers/plans/2026-11-10-week9-today-priority.md
git commit -m "docs: add the week 9 today priority spec and plan"
```

---

## 判断メモ

- **優先度を保存せず読み取り時に計算する理由:** 補正は現在時刻に依存する。保存すると時間とともに古くなり、再計算の job が要る。件数が小さい間は読み取りで足りる。
- **時刻の絞り込みを SQL に置かない理由:** 日の終わりの判定(夏時間を含む)を純粋関数の 1 か所に置き、テストで固定するため。候補は未完了のシナリオだけで、件数は小さい。
- `due_at` **を Worker で求める理由:** timezone と「今日」の基準を記録した時点で固定でき、Today の取得が単純になる。プロフィールの timezone を後で変えても過去の `due_at` は変わらない(Spec で許容)。
- `urgency` **の label を変えない理由:** Week 5 で `normal` 固定と決めた。優先度は score から直接計算するので、label を変えても Today の結果は変わらない。
- `/captures/today` **にした理由:** `app/captures/layout.tsx` の書体・色・ヘッダーをそのまま使うため。route group への移動は既存のテストの import を変えるので避けた。`today` は静的 segment なので `[captureId]` より先に解決される。
- **`zone_for` を `core/timezone.py` に置く理由:** `due.py` と `today.py` が共有し、Week 10 のダイジェスト(ユーザーの timezone と夏時間)も使うため。`today.py` が `due.py` に依存する形を避ける。
- **`local_day_end` に時刻の引数を足さない理由:** 日の終わりは翌日 0 時に固定で、`now` が暦日を決める。時刻を動かす引数は、方針にない「朝 4 時までは前日」のような仕様を呼び込む。必要になったときに足す。
- **timezone を** `CaptureRepository` **で読む理由:** プロフィール用の module はまだ無く、`captures` が既に `profiles` を参照している。専用 module は設定 UI を作る週に切り出す。
- **承認済み(2026-11-10):** `profiles.timezone` の既定を `Asia/Tokyo` にし、既存の `UTC` を書き換える migration(Task 3)。ローカル以外に環境が無い間の措置。
- **確認済み(2026-11-10):** 期限の無い過去の `reminder` は backfill せず、完了にするまで Today に出続ける。Today の URL は `/captures/today`。
