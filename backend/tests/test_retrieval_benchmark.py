import json
from pathlib import Path

from app.services.retrieval_benchmark import (
    BENCHMARK_CATEGORIES,
    BenchmarkCase,
    BenchmarkTarget,
    RetrievalBenchmark,
    acceptance_gate,
    aggregate_benchmark_metrics,
    grouped_ranking_metrics,
    grouped_scoped_ranking_metrics,
    load_benchmark,
    validate_benchmark,
)


def _target(qid: str, group: str | None = None) -> BenchmarkTarget:
    return BenchmarkTarget(
        group=group or qid,
        kind="narrative_passage",
        subject_qid=qid,
        source_revision="12345",
        section_locator="plot",
        content_hash="a" * 64,
    )


def test_grouped_metrics_require_both_films_for_complete_comparison_recall() -> None:
    metrics = grouped_ranking_metrics(
        ["film-a-target", "other"],
        {"Q1": {"film-a-target"}, "Q2": {"film-b-target"}},
        cutoff=10,
    )

    assert metrics["target_group_recall"] == 0.5
    assert metrics["complete_case_recall"] == 0
    assert metrics["mean_reciprocal_rank"] == 0.5


def test_scoped_group_metrics_do_not_penalize_the_second_film_list() -> None:
    metrics = grouped_scoped_ranking_metrics(
        {"Q1": ["target-a"], "Q2": ["target-b"]},
        {"Q1": {"target-a"}, "Q2": {"target-b"}},
    )

    assert metrics["complete_case_recall"] == 1
    assert metrics["mean_reciprocal_rank"] == 1.0


def test_manifest_validation_rejects_benchmark_that_only_looks_large() -> None:
    repeated_case = BenchmarkCase(
        case_id="duplicate",
        category=BENCHMARK_CATEGORIES[0],
        split="test",
        question_id="benchmark.story",
        question_text="What happens?",
        evidence_class="narrative_extraction",
        subject_qids=("Q1",),
        adversarial=False,
        challenge_tags=(),
        targets=(_target("Q1"),),
    )

    try:
        validate_benchmark(RetrievalBenchmark("v1", "assistant_reviewed", (repeated_case,) * 200))
    except ValueError as exc:
        assert "case_id values must be unique" in str(exc)
        assert "question_text values must be unique" in str(exc)
        assert "category" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("invalid benchmark was accepted")


def test_acceptance_gate_enforces_overall_and_per_category_quality() -> None:
    rows = []
    for category in BENCHMARK_CATEGORIES:
        for _ in range(40):
            rows.append({
                "category": category,
                "target_group_recall": 1.0,
                "complete_case_recall": 1,
                "mean_reciprocal_rank": 0.8,
            })
    metrics = aggregate_benchmark_metrics(rows)

    assert acceptance_gate(metrics)["passed"] is True


def test_v1_fixture_is_balanced_and_contains_only_evidence_fingerprints() -> None:
    fixture = Path(__file__).parent / "fixtures" / "retrieval-benchmark-v1.json"
    benchmark = load_benchmark(fixture)

    assert len(benchmark.cases) == 200
    assert {case.category for case in benchmark.cases} == set(BENCHMARK_CATEGORIES)
    assert all(target.content_hash or target.object_qid or target.value_hash for case in benchmark.cases for target in case.targets)
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    assert all("content" not in target for case in payload["cases"] for target in case["targets"])
