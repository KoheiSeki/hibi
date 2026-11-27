"""評価の指標を計算する。

すべて純粋関数で、入力を変えず、外部の状態に触れない。分母が 0 になる指標は、
例外にせず 0.0 を返す。評価データの一部の label に件数が無くても、
レポート全体の計算を止めないため。
"""

import statistics
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from decimal import Decimal
from math import ceil, log2


@dataclass(frozen=True)
class LabelScores:
    """1 つの label の precision、recall、F1。

    Attributes:
        precision: その label と予測したうち、正しかった割合。予測が 0 件なら 0.0。
        recall: 正解がその label のうち、正しく予測できた割合。正解が 0 件なら 0.0。
        f1: precision と recall の調和平均。どちらも 0.0 なら 0.0。
        support: 正解がその label の件数。macro-F1 は support が 0 の label を外して平均する。
    """

    precision: float
    recall: float
    f1: float
    support: int


@dataclass(frozen=True)
class CalibrationBin:
    """confidence の 1 つの区間と、その区間での正解率。

    Attributes:
        lower: 区間の下限で、その値を含む。
        upper: 区間の上限で、その値を含まない。最後の区間だけは 1.0 を含む。
        count: この区間に入ったケースの件数。
        accuracy: この区間での正解率。件数が 0 なら None。0.0 と区別し、
            「全部外れた」と「データが無い」を取り違えないようにする。
    """

    lower: float
    upper: float
    count: int
    accuracy: float | None


def accuracy(expected: Sequence[str], predicted: Sequence[str]) -> float:
    """予測が正解と一致した割合を返す。

    Args:
        expected: 正解の label。
        predicted: 予測の label。expected と同じ順、同じ件数。

    Returns:
        一致した割合。0 件なら 0.0。

    Raises:
        ValueError: expected と predicted の件数が違うとき。
    """

    pairs = _paired(expected, predicted)
    correct = sum(exp == pred for exp, pred in pairs)
    return _safe_divide(correct, len(pairs))


def per_label_scores(
    expected: Sequence[str], predicted: Sequence[str], *, labels: Sequence[str]
) -> dict[str, LabelScores]:
    """label ごとの precision、recall、F1 を計算する。

    labels に無い予測 (`"error"` など) は、どの label の正解としても数えない。
    その結果、正解の label の recall だけが下がる。

    Args:
        expected: 正解の label。
        predicted: 予測の label。expected と同じ順、同じ件数。
        labels: 計算する label。戻り値の dict もこの順に並ぶ。

    Returns:
        label ごとの指標。件数の無い label も、すべて 0 の指標で含める。

    Raises:
        ValueError: expected と predicted の件数が違うとき。
    """

    pairs = _paired(expected, predicted)
    scores: dict[str, LabelScores] = {}
    for label in labels:
        true_positive = sum(exp == label and pred == label for exp, pred in pairs)
        false_positive = sum(exp != label and pred == label for exp, pred in pairs)
        false_negative = sum(exp == label and pred != label for exp, pred in pairs)
        scores[label] = _scores_from_counts(
            true_positive=true_positive,
            false_positive=false_positive,
            false_negative=false_negative,
        )
    return scores


def macro_f1(scores: Mapping[str, LabelScores]) -> float:
    """label ごとの F1 の単純平均を返す。

    support が 0 の label は平均から外す。評価データに無い label の F1 は必ず 0.0 になり、
    含めると、データの偏りが分類器の弱さのように見えてしまうため。

    Args:
        scores: per_label_scores の戻り値。

    Returns:
        F1 の平均。support のある label が 1 つも無ければ 0.0。
    """

    supported_f1_scores: list[float] = [score.f1 for score in scores.values() if score.support > 0]
    return _safe_divide(sum(supported_f1_scores), len(supported_f1_scores))


def confusion_matrix(
    expected: Sequence[str], predicted: Sequence[str], *, labels: Sequence[str]
) -> dict[str, dict[str, int]]:
    """正解と予測の組み合わせごとの件数を数える。

    行は正解、列は予測。labels に無い予測 ("error" など) も列に加える。分類器の失敗を
    隠さずにレポートの表へ出すため。

    Args:
        expected: 正解の label。
        predicted: 予測の label。expected と同じ順、同じ件数。
        labels: 行と列に並べる label。

    Returns:
        matrix[正解][予測] が件数の表。行は labels の順。列は labels の順の後に、
        labels に無い予測を名前の順で並べる。件数が 0 の組み合わせも 0 として含める。

    Raises:
        ValueError: expected と predicted の件数が違うとき。
    """

    pairs = _paired(expected, predicted)
    unknown_predictions = sorted(set(predicted) - set(labels))
    columns = [*labels, *unknown_predictions]
    matrix: dict[str, dict[str, int]] = {row: dict.fromkeys(columns, 0) for row in labels}
    for exp, pred in pairs:
        matrix[exp][pred] += 1
    return matrix


def binary_scores(expected: Sequence[bool], predicted: Sequence[bool]) -> LabelScores:
    """True を陽性として、2 値の precision、recall、F1 を計算する。

    聞き返すべき記録を、聞き返せたかを見るのに使う。

    Args:
        expected: 正解。True なら聞き返すべき。
        predicted: 予測。True なら聞き返した。expected と同じ順、同じ件数。

    Returns:
        陽性の指標。support は正解が True の件数。

    Raises:
        ValueError: expected と predicted の件数が違うとき。
    """

    pairs = _paired(expected, predicted)
    true_positive = sum(exp and pred for exp, pred in pairs)
    false_positive = sum(not exp and pred for exp, pred in pairs)
    false_negative = sum(exp and not pred for exp, pred in pairs)
    return _scores_from_counts(
        true_positive=true_positive, false_positive=false_positive, false_negative=false_negative
    )


def calibration_bins(
    confidences: Sequence[float], correct: Sequence[bool], *, bin_count: int = 10
) -> list[CalibrationBin]:
    """confidence を等幅の区間に分け、区間ごとの件数と正解率を数える。

    区間の番号は、confidence を Decimal に直してから掛けて求める。浮動小数のまま
    掛けると、0.57 * 100 が 56.99… になり、1 つ下の区間に落ちるため。1.0 は
    最後の区間に入れる。

    Args:
        confidences: 予測の confidence。0 以上 1 以下。
        correct: 予測が正しかったか。confidences と同じ順、同じ件数。
        bin_count: 区間の数。

    Returns:
        区間の下限の順に並んだ、bin_count 個の区間。件数が 0 の区間も含める。

    Raises:
        ValueError: confidences と correct の件数が違うとき。
    """

    pairs = _paired(confidences, correct)
    counts = [0] * bin_count
    correct_counts = [0] * bin_count
    for confidence, is_correct in pairs:
        index = min(int(Decimal(str(confidence)) * bin_count), bin_count - 1)
        counts[index] += 1
        if is_correct:
            correct_counts[index] += 1

    bins = []
    for i in range(bin_count):
        lower = i / bin_count
        upper = (i + 1) / bin_count
        bin_accuracy = correct_counts[i] / counts[i] if counts[i] > 0 else None
        bins.append(
            CalibrationBin(lower=lower, upper=upper, count=counts[i], accuracy=bin_accuracy)
        )
    return bins


def percentile(values: Sequence[float], q: float) -> float | None:
    """nearest-rank 法で、q パーセンタイルの値を返す。

    補間をせず、実際に観測した値のどれかを返す。レポートの遅延の値を、
    実際の 1 回の実行に対応付けられるようにするため。

    Args:
        values: 値の列。並び順は問わない。
        q: 0 以上 100 以下のパーセント。0 なら最小値、100 なら最大値。

    Returns:
        昇順に並べて ceil(q * n / 100) 番目 (1 始まり、最小で 1 番目) の値。
        空なら None。

    Raises:
        ValueError: q が 0 以上 100 以下でないとき。
    """

    if not 0 <= q <= 100:
        raise ValueError(f"q must be between 0 and 100, got {q}")
    if not values:
        return None

    rank = max(1, ceil(len(values) * q / 100))
    return sorted(values)[rank - 1]


def recall_at_k(ranked: Sequence[str], relevant: AbstractSet[str], k: int) -> float:
    """上位 k 件に入った正解の割合を返す。

    Args:
        ranked: 検索結果の ID。上位から順。
        relevant: 正解の ID。
        k: 見る件数。

    Returns:
        上位 k 件の中の正解の件数を、正解の総数で割った値。正解が無ければ 0.0。
    """

    hit_count = len(set(ranked[:k]) & relevant)
    return _safe_divide(hit_count, len(relevant))


def reciprocal_rank(ranked: Sequence[str], relevant: AbstractSet[str]) -> float:
    """最初の正解の順位の逆数を返す。

    query ごとの値を平均すると、MRR になる。

    Args:
        ranked: 検索結果の ID。上位から順。
        relevant: 正解の ID。

    Returns:
        最初の正解が r 番目 (1 始まり) なら 1 / r。正解が結果に無ければ 0.0。
    """

    for rank, doc_id in enumerate(ranked, start=1):
        if doc_id in relevant:
            return 1 / rank
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: AbstractSet[str], k: int) -> float:
    """上位 k 件の nDCG を返す。関連は 2 値で、割引は 1 / log2(順位 + 1)。

    理想の並びは、正解を上位に詰めた並びで、上位 k 件までで数える。正解が k 件より
    多いときに全件で数えると、完全な並びでも 1.0 に届かなくなるため。

    Args:
        ranked: 検索結果の ID。上位から順。
        relevant: 正解の ID。
        k: 見る件数。

    Returns:
        実際の DCG を理想の DCG で割った値。0.0 以上 1.0 以下。正解が無ければ 0.0。
    """

    dcg: float = 0.0
    for rank, doc_id in enumerate(ranked[:k], start=1):
        if doc_id in relevant:
            dcg += 1 / log2(rank + 1)

    idcg: float = 0.0
    ideal_count = min(len(relevant), k)
    for rank in range(1, ideal_count + 1):
        idcg += 1 / log2(rank + 1)
    return _safe_divide(dcg, idcg)


def mean_and_std(values: Sequence[float]) -> tuple[float, float]:
    """平均と標本標準偏差を返す。

    同じ評価を複数回実行したときの、ばらつきを見るのに使う。標本標準偏差は
    n - 1 で割る。

    Args:
        values: 値の列。1 件以上。

    Returns:
        平均と標本標準偏差。1 件なら標準偏差は 0.0。

    Raises:
        statistics.StatisticsError: values が空のとき。
    """

    if not values:
        raise statistics.StatisticsError("mean_and_std requires at least one value, got none")
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    return (mean, std)


def _paired[A, B](first: Sequence[A], second: Sequence[B]) -> list[tuple[A, B]]:
    """同じ件数の 2 つの列を、先頭から 1 件ずつ組にする。件数が違えば止める。

    正解と予測、confidence と正誤のように、同じケースについての値を並べた列を
    組にするのに使う。`zip` は黙って短い方に揃えるので、件数の違う結果で
    指標を出してしまう。件数を先に確かめて、ValueError で止める。

    Args:
        first: 1 つ目の列。
        second: 2 つ目の列。first と同じ件数。

    Returns:
        `(first[i], second[i])` の組の list。

    Raises:
        ValueError: first と second の件数が違うとき。
    """

    if len(first) != len(second):
        raise ValueError(f"sequences have different lengths: {len(first)} and {len(second)}")
    return list(zip(first, second, strict=True))


def _safe_divide(numerator: float, denominator: float) -> float:
    """分母が 0 なら 0.0 を返す割り算。"""

    if denominator == 0.0:
        return 0.0
    return numerator / denominator


def _scores_from_counts(
    *, true_positive: int, false_positive: int, false_negative: int
) -> LabelScores:
    """陽性の件数から precision、recall、F1 を作る。

    `per_label_scores` と `binary_scores` で、同じ計算を 1 か所にまとめるため。
    support は true_positive と false_negative の和で、正解が陽性の件数になる。

    Args:
        true_positive: 正解も予測も陽性の件数。
        false_positive: 予測だけが陽性の件数。
        false_negative: 正解だけが陽性の件数。

    Returns:
        指標。
    """

    precision = _safe_divide(true_positive, true_positive + false_positive)
    recall = _safe_divide(true_positive, true_positive + false_negative)
    f1 = _safe_divide(2 * precision * recall, precision + recall)
    support = true_positive + false_negative
    return LabelScores(precision=precision, recall=recall, f1=f1, support=support)
