"""Capture の機能の中で共有する、取りうる値と上限。

types、policies、service のどれからも import できるよう、hibi.ai.classification 以外は
import しない。import し合って循環しないようにするため。category は分類器の出力の
約束なので hibi.ai.classification に置き、ここでは route を作るのに使う。
"""

from typing import Literal

from hibi.ai.classification import (
    CAPTURE_CATEGORY_EXPENSE,
    CAPTURE_CATEGORY_REMINDER,
    CAPTURE_CATEGORY_SHOPPING,
)

CAPTURE_AGGREGATE_TYPE = "capture"
CAPTURE_PROCESSING_REQUESTED = "capture.processing_requested"

CAPTURE_STATUS_PENDING = "pending"
CAPTURE_STATUS_PROCESSING = "processing"
CAPTURE_STATUS_COMPLETED = "completed"
CAPTURE_STATUS_FAILED = "failed"

CAPTURE_PROCESSING_MAX_ATTEMPTS = 3

# route は、確信度が閾値以上なら category そのもの、未満なら clarify になる
CAPTURE_ROUTE_SHOPPING = CAPTURE_CATEGORY_SHOPPING
CAPTURE_ROUTE_REMINDER = CAPTURE_CATEGORY_REMINDER
CAPTURE_ROUTE_EXPENSE = CAPTURE_CATEGORY_EXPENSE
CAPTURE_ROUTE_CLARIFY = "clarify"

CAPTURE_SCENARIO_STATUS_PROPOSED = "proposed"
CAPTURE_SCENARIO_STATUS_ACCEPTED = "accepted"
CAPTURE_SCENARIO_ROUTES = frozenset(
    {CAPTURE_ROUTE_SHOPPING, CAPTURE_ROUTE_REMINDER, CAPTURE_ROUTE_EXPENSE}
)

CAPTURE_SEARCH_MODE_KEYWORD = "keyword"
CAPTURE_SEARCH_MODE_SEMANTIC = "semantic"
CAPTURE_SEARCH_LIMIT = 20

TODAY_MAX_LIMIT = 20
TODAY_DEFAULT_LIMIT = 5


CaptureSearchMode = Literal["keyword", "semantic"]
