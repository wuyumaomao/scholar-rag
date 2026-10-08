"""Metrics for the closed-world retrieval benchmark."""

from dataclasses import dataclass
from typing import Collection, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class CaseMetrics:
    """Recall, precision, and reciprocal rank for one benchmark case."""

    recall: float
    precision: float
    precision_returned: float
    reciprocal_rank: float


@dataclass(frozen=True)
class DatasetMetrics:
    """Macro-averaged metrics across benchmark cases."""

    case_count: int
    recall: float
    precision: float
    precision_returned: float
    mrr: float


def _unique_in_order(ids: Iterable[str]) -> list[str]:
    """Keep the first occurrence of each result ID and preserve rank order."""
    unique: list[str] = []
    seen: set[str] = set()
    for item in ids:
        value = str(item)
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def evaluate_ranked_ids(
    ranked_ids: Sequence[str],
    gold_ids: Collection[str],
    *,
    k: int,
) -> CaseMetrics:
    """Score one ranked result list against the relevant IDs.

    Results are deduplicated before scoring so repeated child hits cannot count
    as separate results. Precision uses the requested ``k`` as its denominator,
    matching the usual Precision@k definition.
    """
    if k <= 0:
        raise ValueError("k 必须大于 0")

    ranked = _unique_in_order(ranked_ids)[:k]
    gold = {str(item) for item in gold_ids}
    relevant_count = sum(item in gold for item in ranked)
    recall = relevant_count / len(gold) if gold else 0.0
    precision = relevant_count / k
    precision_returned = relevant_count / len(ranked) if ranked else 0.0
    reciprocal_rank = 0.0
    for rank, item in enumerate(ranked, start=1):
        if item in gold:
            reciprocal_rank = 1.0 / rank
            break

    return CaseMetrics(
        recall=recall,
        precision=precision,
        precision_returned=precision_returned,
        reciprocal_rank=reciprocal_rank,
    )


def evidence_element_ids(case: Mapping[str, object]) -> set[str]:
    """Collect unique gold element IDs from one JSONL benchmark case."""
    evidence = case.get("evidence", [])
    if not isinstance(evidence, list):
        raise ValueError("benchmark case 的 evidence 必须是数组")

    ids: set[str] = set()
    for item in evidence:
        if not isinstance(item, Mapping):
            raise ValueError("benchmark case 的 evidence 项必须是对象")
        element_ids = item.get("element_ids", [])
        if not isinstance(element_ids, list):
            raise ValueError("evidence.element_ids 必须是数组")
        ids.update(str(element_id) for element_id in element_ids)
    return ids


def source_element_ids_from_metadata(
    metadata_items: Sequence[Mapping[str, object]],
) -> list[str]:
    """Flatten parent metadata into a ranked, deduplicated element list."""
    ids: list[str] = []
    seen: set[str] = set()
    for metadata in metadata_items:
        source_ids = metadata.get("source_element_ids", [])
        if not isinstance(source_ids, list):
            raise ValueError("metadata.source_element_ids 必须是数组")
        for source_id in source_ids:
            value = str(source_id)
            if value in seen:
                continue
            seen.add(value)
            ids.append(value)
    return ids


def retrieval_element_ids_from_metadata(
    metadata_items: Sequence[Mapping[str, object]],
) -> list[str]:
    """Flatten IDs whose text is represented by each ranked result.

    Figure parents keep their own source ID while attaching caption text. The
    optional ``context_element_ids`` field records that relationship; older
    chunks fall back to their original ``source_element_ids``.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for group in retrieval_element_groups_from_metadata(metadata_items):
        for candidate_id in group:
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            ids.append(candidate_id)
    return ids


def retrieval_element_groups_from_metadata(
    metadata_items: Sequence[Mapping[str, object]],
) -> list[list[str]]:
    """Return one covered-element group per ranked parent result."""
    groups: list[list[str]] = []
    for metadata in metadata_items:
        candidate_ids = metadata.get(
            "context_element_ids", metadata.get("source_element_ids", [])
        )
        if not isinstance(candidate_ids, list):
            raise ValueError("metadata context/source element IDs 必须是数组")
        group: list[str] = []
        seen: set[str] = set()
        for candidate_id in candidate_ids:
            value = str(candidate_id)
            if value in seen:
                continue
            seen.add(value)
            group.append(value)
        groups.append(group)
    return groups


def evaluate_ranked_groups(
    ranked_groups: Sequence[Collection[str]],
    gold_ids: Collection[str],
    *,
    k: int,
) -> CaseMetrics:
    """Score ranked parent results where each result covers several IDs."""
    if k <= 0:
        raise ValueError("k 必须大于 0")

    groups = [
        {str(item) for item in group}
        for group in ranked_groups[:k]
    ]
    gold = {str(item) for item in gold_ids}
    matched_gold: set[str] = set()
    relevant_count = 0
    reciprocal_rank = 0.0
    for rank, group in enumerate(groups, start=1):
        matched = group & gold
        matched_gold.update(matched)
        if matched:
            relevant_count += 1
            if reciprocal_rank == 0.0:
                reciprocal_rank = 1.0 / rank

    return CaseMetrics(
        recall=len(matched_gold) / len(gold) if gold else 0.0,
        precision=relevant_count / k,
        precision_returned=relevant_count / len(groups) if groups else 0.0,
        reciprocal_rank=reciprocal_rank,
    )


def evaluate_dataset(
    cases: Sequence[Mapping[str, object]],
    ranked_results: Sequence[Sequence[str]],
    *,
    k: int,
) -> DatasetMetrics:
    """Return macro averages for aligned benchmark cases and result lists."""
    if len(cases) != len(ranked_results):
        raise ValueError("cases 和 ranked_results 数量必须一致")
    if not cases:
        raise ValueError("至少需要一个 benchmark case")

    scores = [
        evaluate_ranked_ids(result, evidence_element_ids(case), k=k)
        for case, result in zip(cases, ranked_results)
    ]
    count = len(scores)
    return DatasetMetrics(
        case_count=count,
        recall=sum(score.recall for score in scores) / count,
        precision=sum(score.precision for score in scores) / count,
        precision_returned=sum(score.precision_returned for score in scores) / count,
        mrr=sum(score.reciprocal_rank for score in scores) / count,
    )
