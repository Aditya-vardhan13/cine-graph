from collections import Counter
from pathlib import Path

from app.services.writer_study import render_packet, technical_checks
from app.services.writer_study_v2 import aggregate_passage_reviews, expected_passage_sources, load_tasks


def test_v2_manifest_covers_current_entry_flows_and_categories() -> None:
    manifest = load_tasks(Path(__file__).parent / "fixtures" / "writer-study-v2.json")

    assert Counter(task["entry"] for task in manifest["tasks"]) == {
        "pair": 12, "film_first": 4, "question_only": 4,
    }
    assert sum(task["category"] == "unanswerable" for task in manifest["tasks"]) >= 2


def test_v2_packet_shows_discovery_and_explicit_abstention() -> None:
    report = {"version": "writer-study-v2", "tasks": [{
        "id": "V01", "category": "moral_dilemma", "entry": "question_only",
        "question": "How does a villain test the hero's ethics?", "status": "displayed", "elapsed_ms": 120,
        "discovery": {"method": "lexical", "leads": [{
            "film": {"title": "First"}, "section_title": "Plot", "excerpt": "A source lead",
            "source_url": "https://example.org/first", "source_license": "CC BY-SA 4.0",
            "source_revision": "123",
        }]},
        "comparison": {
            "first": {"title": "First"}, "second": {"title": "Second"},
            "retrieval_method": "not_run", "answerability_status": "insufficient_evidence",
            "answerability_reason": "No matching passage on both sides.",
            "lenses": [], "caution": "Do not infer a relationship.", "degraded": False,
        },
    }]}

    packet = render_packet(report)

    assert "A source lead" in packet
    assert "Insufficient evidence" in packet
    assert "writer-study-v2-review" in packet
    assert technical_checks(report["tasks"][0]["comparison"])["explicit_abstention_available"] is True


def test_passage_review_requires_complete_labels_and_matching_source_pointers() -> None:
    def passage(chunk_id: str) -> dict:
        return {
            "chunk_id": chunk_id, "source_url": f"https://example.org/{chunk_id}",
            "source_revision": "rev-1", "source_license": "CC BY-SA 4.0",
        }

    report = {"tasks": [{
        "id": "V01", "entry": "question_only",
        "discovery": {"leads": [passage("lead-1"), passage("lead-2"), passage("other-lead")]},
        "comparison": {"lenses": [{
            "identifier": "central_question", "first_evidence": passage("first"),
            "second_evidence": passage("second"),
        }, {
            "identifier": "production", "first_evidence": passage("other-first"),
            "second_evidence": passage("other-second"),
        }]},
    }]}
    pointers = expected_passage_sources(report)
    assert len(pointers) == 4  # Only selected leads and the primary evidence pair.
    labels = dict.fromkeys(pointers, "relevant")
    first = {"reviewer": "writer-a", "passages": labels, "passage_sources": pointers}
    second = {"reviewer": "writer-b", "passages": labels, "passage_sources": pointers}

    summary = aggregate_passage_reviews(report, [first, second])

    assert summary == {
        "rated_passages": 4, "both_reviewers_relevant": 4, "exact_label_agreement": 4,
        "selected_discovery_sets": 1, "selected_discovery_sets_both_relevant": 1,
        "focus_pairs": 1, "focus_pairs_both_relevant": 1,
    }
    from pytest import raises
    with raises(ValueError, match="source-bound"):
        aggregate_passage_reviews(report, [first, {**second, "passages": {}}])
    stale = dict(pointers)
    stale["V01:discovery:lead-1"] = {**stale["V01:discovery:lead-1"], "source_revision": "rev-old"}
    with raises(ValueError, match="stale source"):
        aggregate_passage_reviews(report, [first, {**second, "passage_sources": stale}])
