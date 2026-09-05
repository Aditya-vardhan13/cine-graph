from app.services.reranker_evaluation import (
    aggregate_results,
    evaluate_manifest,
    rank_candidate_ids,
)


def test_rank_candidate_ids_is_deterministic_for_ties() -> None:
    candidates = [{"chunk_id": "first"}, {"chunk_id": "second"}, {"chunk_id": "third"}]

    assert rank_candidate_ids(candidates, [0.5, 0.9, 0.5]) == ["second", "first", "third"]


def test_evaluate_manifest_uses_only_declared_target_chunks() -> None:
    manifest = {
        "manifest_version": "cinegraph-reranker-candidates-v1",
        "queries": [{
            "research_answer_id": "answer-1",
            "question_id": "story.choice",
            "question_text": "What choice changes the story?",
            "target_chunk_ids": ["target"],
            "methods": {
                "dense": [
                    {"chunk_id": "other", "document": "irrelevant"},
                    {"chunk_id": "target", "document": "direct answer"},
                ],
            },
        }],
    }
    checkpoints = []

    report = evaluate_manifest(
        manifest,
        score_pairs=lambda pairs: [0.1 if document == "irrelevant" else 0.9 for _, document in pairs],
        checkpoint=checkpoints.append,
    )

    assert report["metrics_by_candidate_method"]["dense"] == {
        "evaluated_queries": 1,
        "recall_at_10": 1.0,
        "mrr_at_10": 1.0,
    }
    assert checkpoints[-1]["completed_queries"] == 1


def test_aggregate_results_handles_empty_input() -> None:
    assert aggregate_results([], cutoff=5) == {
        "evaluated_queries": 0,
        "recall_at_5": 0.0,
        "mrr_at_5": 0.0,
    }
