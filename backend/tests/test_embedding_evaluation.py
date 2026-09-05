import numpy as np

from app.services.embedding_evaluation import (
    _rank_indexes,
    _reranker_candidate_manifest,
    _section_matches_question_route,
    ranking_metrics,
    summary_metrics,
)


class CandidateChunk:
    def __init__(self, chunk_id: str, subject_id: str, section_locator: str) -> None:
        self.id = chunk_id
        self.subject_entity_id = subject_id
        self.section_locator = section_locator


def test_retrieval_metrics_are_based_only_on_explicit_target_chunks() -> None:
    hit = ranking_metrics(["other", "target", "later"], {"target"}, cutoff=3)
    miss = ranking_metrics(["other", "later"], {"target"}, cutoff=3)

    assert hit == {"recall": 1, "reciprocal_rank": 0.5, "first_relevant_rank": 2}
    assert miss == {"recall": 0, "reciprocal_rank": 0.0, "first_relevant_rank": None}
    assert summary_metrics([hit, miss], cutoff=3) == {
        "evaluated_queries": 2,
        "recall_at_3": 0.5,
        "mrr_at_3": 0.25,
    }


def test_rank_indexes_handles_candidate_set_smaller_than_cutoff() -> None:
    scores = np.asarray([0.1, 0.9, 0.4], dtype=np.float32)

    ranked = _rank_indexes(scores, np.asarray([0, 2]), cutoff=10)

    assert ranked.tolist() == [2, 0]


def test_section_route_limits_story_questions_to_plot_evidence() -> None:
    assert _section_matches_question_route(
        section_locator="plot", question_id="story.escape-becomes-return", evidence_class="narrative_extraction",
    )
    assert not _section_matches_question_route(
        section_locator="production/writing",
        question_id="story.escape-becomes-return",
        evidence_class="narrative_extraction",
    )


def test_section_route_does_not_override_source_fact_lane() -> None:
    assert _section_matches_question_route(
        section_locator="production/filming/alternative-endings",
        question_id="story.ending-as-cultural-choice",
        evidence_class="source_fact",
    )


def test_reranker_manifest_exports_only_narrative_questions() -> None:
    chunks = [CandidateChunk("chunk-1", "film-1", "plot")]
    manifest = _reranker_candidate_manifest(
        chunks=chunks,  # type: ignore[arg-type]
        contents=["Film: Example\nSection: Plot\nEvidence: Direct evidence."],
        queries=[
            {
                "research_answer_id": "answer-1", "question_id": "story.choice",
                "question_text": "What choice?", "evidence_class": "narrative_extraction",
                "target_chunk_ids": {"chunk-1"},
            },
            {
                "research_answer_id": "answer-2", "question_id": "release.date",
                "question_text": "When?", "evidence_class": "source_fact",
                "target_chunk_ids": {"chunk-1"},
            },
        ],
        rankings_by_method={"dense": [["chunk-1"], ["chunk-1"]]},
    )

    assert [query["question_id"] for query in manifest["queries"]] == ["story.choice"]
    assert manifest["queries"][0]["methods"]["dense"][0]["section_locator"] == "plot"
