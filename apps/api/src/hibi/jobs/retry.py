"""arq の job が失敗したときに使う、再試行の待ち時間。"""

import random

_BASE_DELAY_SECONDS = 5
_JITTER_SECONDS = 1


def retry_delay(attempt: int) -> float:
    """次の再試行までの待ち時間を、秒で返す。

    試行ごとに倍にする指数バックオフに、ジッターを足す。失敗したジョブが
    同時に再試行して、外部 API に負荷が集中するのを避けるため。

    Args:
        attempt: 失敗した試行の回数。1 始まり。

    Returns:
        待ち時間の秒数。
    """

    exponential_delay = _BASE_DELAY_SECONDS * (2 ** (attempt - 1))
    return exponential_delay + random.uniform(0, _JITTER_SECONDS)
