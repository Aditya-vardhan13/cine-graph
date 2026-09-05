"""Versioned, evidence-fingerprint retrieval benchmark policies.

Benchmark manifests contain questions and source identifiers, never copied
source prose.  Narrative targets resolve through immutable passage hashes;
structured targets resolve through reviewed ``Assertion`` fingerprints.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


BENCHMARK_CATEGORIES = (
    "plot_character_structure",
    "production_craft",
    "reception_legacy",
    "objective_fact",
    "cross_film_comparison",
)
BENCHMARK_SPLITS = ("development", "test")
TARGET_KINDS = ("narrative_passage", "assertion")


@dataclass(frozen=True)
class BenchmarkTarget:
    group: str
    kind: str
    subject_qid: str
    source_revision: str | None = None
    section_locator: str | None = None
    content_hash: str | None = None
    predicate: str | None = None
    object_qid: str | None = None
    value_hash: str | None = None


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    category: str
    split: str
    question_id: str
    question_text: str
    evidence_class: str
    subject_qids: tuple[str, ...]
    adversarial: bool
    challenge_tags: tuple[str, ...]
    targets: tuple[BenchmarkTarget, ...]


@dataclass(frozen=True)
class RetrievalBenchmark:
    version: str
    adjudication_status: str
    cases: tuple[BenchmarkCase, ...]


def _target_from_payload(payload: dict[str, Any]) -> BenchmarkTarget:
    return BenchmarkTarget(
        group=str(payload["group"]),
        kind=str(payload["kind"]),
        subject_qid=str(payload["subject_qid"]),
        source_revision=payload.get("source_revision"),
        section_locator=payload.get("section_locator"),
        content_hash=payload.get("content_hash"),
        predicate=payload.get("predicate"),
        object_qid=payload.get("object_qid"),
        value_hash=payload.get("value_hash"),
    )


def load_benchmark(path: Path) -> RetrievalBenchmark:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = tuple(BenchmarkCase(
        case_id=str(item["case_id"]),
        category=str(item["category"]),
        split=str(item["split"]),
        question_id=str(item["question_id"]),
        question_text=str(item["question_text"]),
        evidence_class=str(item["evidence_class"]),
        subject_qids=tuple(str(qid) for qid in item["subject_qids"]),
        adversarial=bool(item["adversarial"]),
        challenge_tags=tuple(str(tag) for tag in item.get("challenge_tags", [])),
        targets=tuple(_target_from_payload(target) for target in item["targets"]),
    ) for item in payload["cases"])
    benchmark = RetrievalBenchmark(
        version=str(payload["version"]),
        adjudication_status=str(payload["adjudication_status"]),
        cases=cases,
    )
    validate_benchmark(benchmark)
    return benchmark


def validate_benchmark(benchmark: RetrievalBenchmark, *, expected_size: int = 200) -> None:
    errors: list[str] = []
    if len(benchmark.cases) != expected_size:
        errors.append(f"expected {expected_size} cases, found {len(benchmark.cases)}")
    identifiers = [case.case_id for case in benchmark.cases]
    if len(set(identifiers)) != len(identifiers):
        errors.append("case_id values must be unique")
    questions = [case.question_text.casefold().strip() for case in benchmark.cases]
    if len(set(questions)) != len(questions):
        errors.append("question_text values must be unique")
    category_counts = Counter(case.category for case in benchmark.cases)
    for category in BENCHMARK_CATEGORIES:
        if category_counts[category] != expected_size // len(BENCHMARK_CATEGORIES):
            errors.append(f"category {category!r} has {category_counts[category]} cases")
        category_cases = [case for case in benchmark.cases if case.category == category]
        split_counts = Counter(case.split for case in category_cases)
        if split_counts != {"development": 10, "test": 30}:
            errors.append(
                f"category {category!r} must have 10 development and 30 test cases; "
                f"found {dict(split_counts)}"
            )
        if sum(case.adversarial for case in category_cases) < 10:
            errors.append(f"category {category!r} must include at least 10 adversarial cases")

    for case in benchmark.cases:
        if case.category not in BENCHMARK_CATEGORIES:
            errors.append(f"{case.case_id}: invalid category {case.category!r}")
        if case.split not in BENCHMARK_SPLITS:
            errors.append(f"{case.case_id}: invalid split {case.split!r}")
        if not case.question_text.strip() or not case.targets:
            errors.append(f"{case.case_id}: question and targets are required")
        if case.adversarial and not case.challenge_tags:
            errors.append(f"{case.case_id}: adversarial cases require challenge tags")
        expected_subject_count = 2 if case.category == "cross_film_comparison" else 1
        if len(case.subject_qids) != expected_subject_count:
            errors.append(f"{case.case_id}: expected {expected_subject_count} subject QIDs")
        target_groups = {target.group for target in case.targets}
        if case.category == "cross_film_comparison" and target_groups != set(case.subject_qids):
            errors.append(f"{case.case_id}: cross-film targets must cover both subject QIDs")
        for target in case.targets:
            if target.kind not in TARGET_KINDS:
                errors.append(f"{case.case_id}: invalid target kind {target.kind!r}")
            if target.subject_qid not in case.subject_qids:
                errors.append(f"{case.case_id}: target subject is outside query scope")
            if target.kind == "narrative_passage":
                if not target.section_locator or not target.source_revision:
                    errors.append(f"{case.case_id}: narrative target requires locator and source revision")
                if not target.content_hash or len(target.content_hash) != 64:
                    errors.append(f"{case.case_id}: narrative target requires a SHA-256 content hash")
                if target.predicate or target.object_qid or target.value_hash:
                    errors.append(f"{case.case_id}: narrative target contains structured fields")
            if target.kind == "assertion":
                if not target.predicate or not (target.object_qid or target.value_hash):
                    errors.append(f"{case.case_id}: assertion target requires predicate and object/value fingerprint")
                if target.content_hash or target.section_locator:
                    errors.append(f"{case.case_id}: assertion target contains narrative fields")
    if errors:
        raise ValueError("Invalid retrieval benchmark:\n- " + "\n- ".join(errors))


def grouped_ranking_metrics(
    ranked_identifiers: Iterable[str],
    relevant_groups: dict[str, set[str]],
    *,
    cutoff: int = 10,
) -> dict[str, Any]:
    ranked = list(ranked_identifiers)[:cutoff]
    reciprocal_ranks: list[float] = []
    group_ranks: dict[str, int | None] = {}
    for group, targets in relevant_groups.items():
        rank = next((position for position, identifier in enumerate(ranked, start=1) if identifier in targets), None)
        group_ranks[group] = rank
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    groups_found = sum(rank is not None for rank in group_ranks.values())
    group_count = len(group_ranks)
    return {
        "target_group_recall": groups_found / group_count if group_count else 0.0,
        "complete_case_recall": int(bool(group_count) and groups_found == group_count),
        "mean_reciprocal_rank": sum(reciprocal_ranks) / group_count if group_count else 0.0,
        "first_relevant_ranks": group_ranks,
    }


def grouped_scoped_ranking_metrics(
    rankings_by_group: dict[str, Iterable[str]],
    relevant_groups: dict[str, set[str]],
    *,
    cutoff: int = 10,
) -> dict[str, Any]:
    """Score multi-film evidence while keeping each film's rank list separate."""
    group_ranks: dict[str, int | None] = {}
    for group, targets in relevant_groups.items():
        ranking = list(rankings_by_group.get(group, ()))[:cutoff]
        group_ranks[group] = next(
            (position for position, identifier in enumerate(ranking, start=1) if identifier in targets),
            None,
        )
    groups_found = sum(rank is not None for rank in group_ranks.values())
    group_count = len(group_ranks)
    return {
        "target_group_recall": groups_found / group_count if group_count else 0.0,
        "complete_case_recall": int(bool(group_count) and groups_found == group_count),
        "mean_reciprocal_rank": (
            sum(1 / rank if rank else 0.0 for rank in group_ranks.values()) / group_count
            if group_count else 0.0
        ),
        "first_relevant_ranks": group_ranks,
    }


def aggregate_benchmark_metrics(rows: Iterable[dict[str, Any]], *, cutoff: int = 10) -> dict[str, Any]:
    materialized = list(rows)
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in materialized:
        by_category[str(row["category"])].append(row)

    def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
        if not items:
            return {"cases": 0, f"target_group_recall_at_{cutoff}": 0.0, f"complete_case_recall_at_{cutoff}": 0.0, f"mrr_at_{cutoff}": 0.0}
        return {
            "cases": len(items),
            f"target_group_recall_at_{cutoff}": round(sum(item["target_group_recall"] for item in items) / len(items), 4),
            f"complete_case_recall_at_{cutoff}": round(sum(item["complete_case_recall"] for item in items) / len(items), 4),
            f"mrr_at_{cutoff}": round(sum(item["mean_reciprocal_rank"] for item in items) / len(items), 4),
        }

    return {
        "overall": summarize(materialized),
        "by_category": {category: summarize(by_category[category]) for category in BENCHMARK_CATEGORIES},
    }


def acceptance_gate(metrics: dict[str, Any], *, cutoff: int = 10) -> dict[str, Any]:
    overall = metrics["overall"]
    category_metrics = metrics["by_category"]
    checks = {
        "overall_target_recall": overall[f"target_group_recall_at_{cutoff}"] >= 0.90,
        "overall_mrr": overall[f"mrr_at_{cutoff}"] >= 0.70,
        "every_category_recall": all(
            values[f"target_group_recall_at_{cutoff}"] >= 0.85 for values in category_metrics.values()
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}
