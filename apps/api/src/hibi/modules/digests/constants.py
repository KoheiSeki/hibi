"""ダイジェストと週次レビューの機能の中で共有する、取りうる値と上限。

types、service、router のどれからも import できるよう、他の file は import しない。
import し合って循環しないようにするため。
"""

from typing import Literal

DIGEST_AGGREGATE_TYPE = "digest_report"
DIGEST_GENERATION_REQUESTED = "digest_report.generation_requested"
DIGEST_KIND_DAILY = "daily"
DIGEST_KIND_WEEKLY = "weekly"
DIGEST_STATUS_PENDING = "pending"
DIGEST_STATUS_READY = "ready"
DIGEST_STATUS_FAILED = "failed"

DIGEST_GENERATION_MAX_ATTEMPTS = 3

# 取り得る値を型で表す。DB の check と同じ値で、API の OpenAPI と、生成される client の型にも出る
DigestKind = Literal["daily", "weekly"]
DigestStatus = Literal["pending", "ready", "failed"]

DIGEST_ERROR_GENERATION_FAILED = "generation_failed"
DIGEST_ERROR_REVIEW_PROVIDER = "review_provider_error"

DIGEST_LIST_DEFAULT_LIMIT = 7
DIGEST_LIST_MAX_LIMIT = 30
