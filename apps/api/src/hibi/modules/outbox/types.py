from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    """配送待ちの outbox 1 件のうち、arq に投入するのに必要な項目。

    Attributes:
        id: outbox の id。job の重複防止の id に使う。
        aggregate_id: 処理する対象の id。`aggregate_type` が capture なら Capture、
            digest_report ならダイジェストの行。
        aggregate_type: 対象の種類。relay は、これで投入する job を選ぶ。
        processing_generation: 依頼した処理の世代。digest は世代を持たず、常に 1。
    """

    id: UUID
    aggregate_id: UUID
    aggregate_type: str
    processing_generation: int
