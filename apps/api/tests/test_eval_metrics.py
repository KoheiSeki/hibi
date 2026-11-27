import math

import pytest

from hibi.evals.metrics import (
    CalibrationBin,
    LabelScores,
    accuracy,
    binary_scores,
    calibration_bins,
    confusion_matrix,
    macro_f1,
    mean_and_std,
    ndcg_at_k,
    per_label_scores,
    percentile,
    recall_at_k,
    reciprocal_rank,
)

_EXPECTED = ["shopping", "shopping", "note", "chat"]
_PREDICTED = ["shopping", "note", "note", "chat"]
_LABELS = ["shopping", "reminder", "expense", "note", "chat"]


def test_accuracy() -> None:
    assert accuracy(_EXPECTED, _PREDICTED) == 0.75
    assert accuracy([], []) == 0.0


def test_accuracy_rejects_sequences_of_different_lengths() -> None:
    # zip で黙って短い方に揃えると、件数の違う結果で指標を出してしまう
    with pytest.raises(ValueError):
        accuracy(["shopping", "note"], ["shopping"])


def test_per_label_scores_and_macro_f1() -> None:
    scores = per_label_scores(_EXPECTED, _PREDICTED, labels=_LABELS)

    assert list(scores) == _LABELS
    assert scores["shopping"] == LabelScores(
        precision=1.0, recall=0.5, f1=pytest.approx(2 / 3), support=2
    )
    assert scores["note"].precision == 0.5
    assert scores["note"].recall == 1.0
    assert scores["reminder"] == LabelScores(precision=0.0, recall=0.0, f1=0.0, support=0)
    assert macro_f1(scores) == pytest.approx((2 / 3 + 2 / 3 + 1.0) / 3)


def test_per_label_scores_for_a_label_that_is_only_predicted() -> None:
    # 正解には無い label を予測しても、割り算で落ちず、recall は 0.0 になる
    scores = per_label_scores(["shopping"], ["note"], labels=_LABELS)

    assert scores["note"] == LabelScores(precision=0.0, recall=0.0, f1=0.0, support=0)
    assert scores["shopping"] == LabelScores(precision=0.0, recall=0.0, f1=0.0, support=1)


def test_macro_f1_without_any_supported_label_is_zero() -> None:
    scores = per_label_scores([], [], labels=_LABELS)

    assert macro_f1(scores) == 0.0


def test_confusion_matrix_keeps_unknown_predictions() -> None:
    matrix = confusion_matrix(["shopping", "note"], ["note", "error"], labels=_LABELS)

    assert list(matrix) == _LABELS
    assert list(matrix["shopping"]) == [*_LABELS, "error"]
    assert matrix["shopping"]["note"] == 1
    assert matrix["note"]["error"] == 1
    assert matrix["reminder"] == dict.fromkeys([*_LABELS, "error"], 0)


def test_binary_scores() -> None:
    assert binary_scores([True, True, False], [True, False, True]) == LabelScores(
        precision=0.5, recall=0.5, f1=0.5, support=2
    )
    # 聞き返すべき 2 件のうち 1 件だけ聞き返した。FP と FN の取り違えを見つけるため、非対称にする
    assert binary_scores([True, True], [True, False]) == LabelScores(
        precision=1.0, recall=0.5, f1=pytest.approx(2 / 3), support=2
    )
    assert binary_scores([False], [False]) == LabelScores(
        precision=0.0, recall=0.0, f1=0.0, support=0
    )


def test_calibration_bins_put_one_in_the_last_bin() -> None:
    bins = calibration_bins([0.95, 0.72, 0.65, 1.0], [True, False, True, True])

    assert len(bins) == 10
    assert bins[0] == CalibrationBin(lower=0.0, upper=0.1, count=0, accuracy=None)
    assert bins[7] == CalibrationBin(lower=0.7, upper=0.8, count=1, accuracy=0.0)
    assert (bins[6].count, bins[6].accuracy) == (1, 1.0)
    assert (bins[9].count, bins[9].accuracy) == (2, 1.0)


def test_calibration_bins_do_not_shift_on_float_error() -> None:
    # 0.57 * 100 は浮動小数では 56.99999999999999 になり、int で 56 の区間に落ちる
    bins = calibration_bins([0.57, 0.29], [True, True], bin_count=100)

    assert bins[57].count == 1
    assert bins[29].count == 1


def test_percentile_uses_nearest_rank() -> None:
    assert percentile([40, 10, 30, 20], 50) == 20
    assert percentile([40, 10, 30, 20], 95) == 40
    assert percentile([40, 10, 30, 20], 0) == 10
    assert percentile([40, 10, 30, 20], 100) == 40
    assert percentile([], 50) is None


def test_retrieval_metrics() -> None:
    ranked, relevant = ["d3", "d1", "d2"], {"d1", "d2"}

    assert recall_at_k(ranked, relevant, 1) == 0.0
    assert recall_at_k(ranked, relevant, 2) == 0.5
    assert recall_at_k(ranked, relevant, 3) == 1.0
    assert reciprocal_rank(ranked, relevant) == 0.5
    assert reciprocal_rank(["d9"], relevant) == 0.0
    assert ndcg_at_k(ranked, relevant, 3) == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    )


def test_ndcg_limits_the_ideal_ranking_to_k() -> None:
    # 正解が 3 件でも、理想の並びは上位 k 件までで数える
    assert ndcg_at_k(["d1", "d9"], {"d1", "d2", "d3"}, 2) == pytest.approx(
        1 / (1 + 1 / math.log2(3))
    )
    assert ndcg_at_k(["d1", "d2"], {"d1", "d2", "d3"}, 2) == pytest.approx(1.0)


def test_retrieval_metrics_without_relevant_docs_are_zero() -> None:
    assert recall_at_k(["d1"], set(), 5) == 0.0
    assert reciprocal_rank(["d1"], set()) == 0.0
    assert ndcg_at_k(["d1"], set(), 5) == 0.0


def test_mean_and_std() -> None:
    assert mean_and_std([0.8]) == (0.8, 0.0)
    assert mean_and_std([0.7, 0.9]) == (pytest.approx(0.8), pytest.approx(0.14142, abs=1e-5))
