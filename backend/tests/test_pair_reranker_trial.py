import pytest

from app.services.pair_reranker_trial import reranker_document, reranker_query
from app.services.pair_mlx_reranker_trial import mlx_runtime_limits, select_trial_cases


def test_mlx_runtime_defaults_are_explicit_and_process_local() -> None:
    assert mlx_runtime_limits() == {
        "memory_limit_bytes": 4 * 1024**3, "cache_limit_bytes": 128 * 1024**2,
    }
    assert mlx_runtime_limits(cache_limit_mb=0)["cache_limit_bytes"] == 0


@pytest.mark.parametrize("memory,cache", [
    (0, 128), (-1, 128), (float("nan"), 128), (float("inf"), 128),
    (4, -1), (4, float("nan")), (4, float("inf")), (1, 2048),
])
def test_mlx_runtime_rejects_unsafe_or_nonfinite_settings(memory: float, cache: float) -> None:
    with pytest.raises(ValueError):
        mlx_runtime_limits(memory_limit_gb=memory, cache_limit_mb=cache)


def test_reranker_query_can_name_both_sides_of_the_comparison() -> None:
    assert reranker_query("Compare the choices", "Film A", "Film B") == (
        "Film: Film A\nComparison film: Film B\nResearch question: Compare the choices"
    )


def test_mlx_trial_can_select_one_case_for_capture_diff_diagnostics() -> None:
    cases = [{"case_id": "P01-Q1"}, {"case_id": "P04-Q5"}]
    assert select_trial_cases(cases, "P04-Q5") == [cases[1]]
    assert select_trial_cases(cases, None) is cases
    with pytest.raises(ValueError, match="exactly one captured case"):
        select_trial_cases(cases, "missing")


def test_reranker_document_adds_context_without_rewriting_source_passage() -> None:
    assert reranker_document("A source sentence.") == "A source sentence."
    assert reranker_document(
        "A source sentence.", film_title="Example Film", section_title="Plot",
    ) == "Film: Example Film\nSection: Plot\nEvidence: A source sentence."


def test_reranker_document_supports_partial_context() -> None:
    assert reranker_document("A source sentence.", section_title="Reception") == (
        "Section: Reception\nEvidence: A source sentence."
    )
