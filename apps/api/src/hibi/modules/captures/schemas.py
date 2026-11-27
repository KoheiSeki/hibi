from datetime import datetime
from uuid import UUID

from hibi.core.models import ApiModel


class CreateCaptureRequest(ApiModel):
    """記録の作成の入力。

    rawText は前後の空白を除いて 1 文字以上 2000 文字以下。違反は 422。
    """

    raw_text: str


class UpdateCaptureRequest(ApiModel):
    """記録の本文の更新の入力。

    rawText は作成のときと同じ制約。更新できるのは pending と failed の記録だけ。
    """

    raw_text: str


class CaptureResponse(ApiModel):
    """記録 1 件。

    status は pending、processing、completed、failed のいずれか。category、route、
    urgency、confidence、policyVersion、questionVersion、processedAt は、処理が
    終わるまで null。clarificationText は、route が clarify のときだけ入る。
    scenario は、completed で route が shopping、reminder、expense のときだけ入る。
    """

    id: UUID
    raw_text: str
    status: str
    created_at: datetime
    updated_at: datetime
    category: str | None = None
    route: str | None = None
    urgency: str | None = None
    confidence: float | None = None
    policy_version: str | None = None
    question_version: str | None = None
    processed_at: datetime | None = None
    clarification_text: str | None = None
    scenario: ScenarioResponse | None = None


class ScenarioResponse(ApiModel):
    """記録から作った、やることの提案と、その進み具合。

    status が proposed なら提案、accepted ならユーザーが確認済み。doneAt が入って
    いれば完了済みで、status とは独立している。amount は支出で金額が取れたときだけ、
    remindText と dueAt は予定で時刻を読み取れたときだけ入る。
    """

    route: str
    status: str
    title: str
    amount: int | None = None
    remind_text: str | None = None
    policy_version: str
    due_at: datetime | None = None
    done_at: datetime | None = None
