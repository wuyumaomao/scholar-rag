import pytest

from app.evaluation import (
    evaluate_dataset,
    evaluate_ranked_groups,
    evaluate_ranked_ids,
    retrieval_element_groups_from_metadata,
    retrieval_element_ids_from_metadata,
    source_element_ids_from_metadata,
)


def test_evaluate_ranked_ids_calculates_recall_precision_and_mrr() -> None:
    metrics = evaluate_ranked_ids(
        ["element-a", "element-x", "element-b"],
        {"element-b", "element-c"},
        k=3,
    )

    assert metrics.recall == pytest.approx(0.5)
    assert metrics.precision == pytest.approx(1 / 3)
    assert metrics.precision_returned == pytest.approx(1 / 3)
    assert metrics.reciprocal_rank == pytest.approx(1 / 3)


def test_evaluate_ranked_ids_deduplicates_results_before_scoring() -> None:
    metrics = evaluate_ranked_ids(
        ["parent-a", "parent-a", "parent-b"],
        {"parent-a"},
        k=3,
    )

    assert metrics.recall == pytest.approx(1.0)
    assert metrics.precision == pytest.approx(1 / 3)
    assert metrics.precision_returned == pytest.approx(0.5)
    assert metrics.reciprocal_rank == pytest.approx(1.0)


def test_evaluate_ranked_ids_returns_zero_when_nothing_matches() -> None:
    metrics = evaluate_ranked_ids(["element-x"], {"element-a"}, k=3)

    assert metrics.recall == 0.0
    assert metrics.precision == 0.0
    assert metrics.precision_returned == 0.0
    assert metrics.reciprocal_rank == 0.0


def test_evaluate_dataset_averages_case_metrics() -> None:
    cases = [
        {"evidence": [{"element_ids": ["element-a"]}]},
        {"evidence": [{"element_ids": ["element-b"]}]},
    ]
    results = [["element-a"], ["element-x"]]

    metrics = evaluate_dataset(cases, results, k=1)

    assert metrics.case_count == 2
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.precision_returned == pytest.approx(0.5)
    assert metrics.mrr == pytest.approx(0.5)


def test_source_element_ids_from_metadata_deduplicates_parent_ids() -> None:
    ranked_ids = source_element_ids_from_metadata(
        [
            {"source_element_ids": ["element-a"]},
            {"source_element_ids": ["element-a", "element-b"]},
            {"source_element_ids": []},
        ]
    )

    assert ranked_ids == ["element-a", "element-b"]


def test_retrieval_element_ids_include_text_attached_to_a_parent() -> None:
    ranked_ids = retrieval_element_ids_from_metadata(
        [
            {
                "source_element_ids": ["element-000065"],
                "context_element_ids": ["element-000065", "element-000066"],
            }
        ]
    )

    assert ranked_ids == ["element-000065", "element-000066"]


def test_retrieval_groups_keep_parent_rank_when_context_has_multiple_elements() -> None:
    groups = retrieval_element_groups_from_metadata(
        [
            {"source_element_ids": ["element-000141"]},
            {
                "source_element_ids": ["element-000065"],
                "context_element_ids": ["element-000065", "element-000066"],
            },
        ]
    )

    metrics = evaluate_ranked_groups(
        groups,
        {"element-000064", "element-000066"},
        k=2,
    )

    assert metrics.recall == pytest.approx(0.5)
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.precision_returned == pytest.approx(0.5)
    assert metrics.reciprocal_rank == pytest.approx(0.5)
