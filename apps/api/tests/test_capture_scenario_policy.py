from datetime import UTC, datetime

import pytest

from hibi.modules.captures.constants import (
    CAPTURE_SCENARIO_STATUS_PROPOSED,
)
from hibi.modules.captures.policies import (
    CAPTURE_SCENARIO_POLICY_VERSION,
    propose_capture_scenario,
)

# 2026-11-10 15:00 JST
NOW = datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
JST = "Asia/Tokyo"


@pytest.mark.parametrize("route", ["shopping", "reminder", "expense"])
def test_propose_capture_scenario_proposes_executable_routes(route: str) -> None:
    proposal = propose_capture_scenario(route=route, raw_text="卵を買う", now=NOW, timezone=JST)

    assert proposal is not None
    assert proposal.route == route
    assert proposal.status == CAPTURE_SCENARIO_STATUS_PROPOSED
    assert proposal.policy_version == CAPTURE_SCENARIO_POLICY_VERSION


@pytest.mark.parametrize("route", ["clarify", "note", "chat"])
def test_propose_capture_scenario_skips_non_executable_routes(route: str) -> None:
    assert (
        propose_capture_scenario(route=route, raw_text="牛乳を買う", now=NOW, timezone=JST) is None
    )


@pytest.mark.parametrize(
    ("route", "raw_text", "title", "amount", "remind_text"),
    [
        ("shopping", "牛乳を買う", "牛乳", None, None),
        ("shopping", "境界の牛乳", "牛乳", None, None),
        ("reminder", "明日の 9 時に起こして", "起こして", None, "明日の 9 時"),
        ("expense", "ランチ 1200 円", "ランチ", 1200, None),
    ],
)
def test_propose_capture_scenario_extracts_known_sentences(
    route: str,
    raw_text: str,
    title: str,
    amount: int | None,
    remind_text: str | None,
) -> None:
    proposal = propose_capture_scenario(
        route=route, raw_text=raw_text, now=NOW, timezone="Asia/Tokyo"
    )

    assert proposal is not None
    assert proposal.title == title
    assert proposal.amount == amount
    assert proposal.remind_text == remind_text


def test_propose_capture_scenario_uses_trimmed_text_for_unknown_shopping() -> None:
    proposal = propose_capture_scenario(
        route="shopping", raw_text=" 卵を買う ", now=NOW, timezone="Asia/Tokyo"
    )

    assert proposal is not None
    assert proposal.title == "卵を買う"
    assert proposal.amount is None
    assert proposal.remind_text is None


def test_propose_capture_scenario_reads_amount_from_unknown_expense() -> None:
    proposal = propose_capture_scenario(
        route="expense", raw_text="コーヒー 500 円", now=NOW, timezone="Asia/Tokyo"
    )

    assert proposal is not None
    assert proposal.title == "コーヒー 500 円"
    assert proposal.amount == 500
    assert proposal.remind_text is None


def test_propose_capture_scenario_leaves_amount_empty_without_yen() -> None:
    proposal = propose_capture_scenario(
        route="expense", raw_text="ランチ", now=NOW, timezone="Asia/Tokyo"
    )

    assert proposal is not None
    assert proposal.title == "ランチ"
    assert proposal.amount is None


def test_propose_capture_scenario_ignores_amount_outside_expense() -> None:
    proposal = propose_capture_scenario(
        route="shopping", raw_text="牛乳 100 円を買う", now=NOW, timezone="Asia/Tokyo"
    )

    assert proposal is not None
    assert proposal.title == "牛乳 100 円を買う"
    assert proposal.amount is None


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


def test_reminder_outside_the_dataset_extracts_the_time_expression() -> None:
    proposal = propose_capture_scenario(
        route="reminder", raw_text="午後3時に会議", now=NOW, timezone=JST
    )

    assert proposal is not None
    assert proposal.remind_text == "午後3時"
    assert proposal.due_at == datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
