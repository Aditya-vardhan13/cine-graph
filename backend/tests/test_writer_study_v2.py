from collections import Counter
import hashlib
import json
from pathlib import Path

from app.services.writer_study import render_packet, technical_checks
from app.services.writer_study_v2 import aggregate_passage_reviews, expected_passage_sources, load_tasks


def test_v2_manifest_covers_current_entry_flows_and_categories() -> None:
    manifest = load_tasks(Path(__file__).parent / "fixtures" / "writer-study-v2.json")

    assert Counter(task["entry"] for task in manifest["tasks"]) == {
        "pair": 12, "film_first": 4, "question_only": 4,
    }
    assert sum(task["category"] == "unanswerable" for task in manifest["tasks"]) >= 2


def test_heldout_manifest_is_frozen_separately_from_development_questions() -> None:
    fixture_dir = Path(__file__).parent / "fixtures"
    development = load_tasks(fixture_dir / "writer-study-v2.json")
    heldout = load_tasks(fixture_dir / "writer-study-v2-heldout.json")

    assert all(task["id"].startswith("H") for task in heldout["tasks"])
    assert {task["question"] for task in heldout["tasks"]}.isdisjoint(
        {task["question"] for task in development["tasks"]}
    )
    assert {frozenset(task["films"]) for task in heldout["tasks"] if task["entry"] == "pair"}.isdisjoint(
        {frozenset(task["films"]) for task in development["tasks"] if task["entry"] == "pair"}
    )


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
    packet_id = hashlib.sha256(json.dumps(report, sort_keys=True).encode("utf-8")).hexdigest()
    first = {"reviewer": "writer-a", "packet_id": packet_id, "passages": labels, "passage_sources": pointers}
    second = {"reviewer": "writer-b", "packet_id": packet_id, "passages": labels, "passage_sources": pointers}

    summary = aggregate_passage_reviews(report, [first, second])

    assert summary == {
        "rated_passages": 4, "both_reviewers_relevant": 4, "exact_label_agreement": 4,
        "discovery_attempts": 1, "discovery_insufficient_leads": 0,
        "selected_discovery_sets": 1, "selected_discovery_sets_both_relevant": 1,
        "focus_pairs": 1, "focus_pairs_both_relevant": 1,
        "per_task": {"V01": {
            "discovery_status": "both_relevant", "primary_pair_status": "both_relevant",
            "selected_passage_ids": [
                "V01:discovery:lead-1", "V01:discovery:lead-2",
                "V01:comparison:central_question:first:first",
                "V01:comparison:central_question:second:second",
            ],
            "disagreement_passage_ids": [],
        }},
    }
    from pytest import raises
    with raises(ValueError, match="source-bound"):
        aggregate_passage_reviews(report, [first, {**second, "passages": {}}])
    stale = dict(pointers)
    stale["V01:discovery:lead-1"] = {**stale["V01:discovery:lead-1"], "source_revision": "rev-old"}
    with raises(ValueError, match="stale source"):
        aggregate_passage_reviews(report, [first, {**second, "passage_sources": stale}])
    with raises(ValueError, match="different study capture"):
        aggregate_passage_reviews(report, [first, {**second, "packet_id": "older-capture"}])


def test_incomplete_discovery_does_not_count_as_a_successful_selection() -> None:
    report = {"tasks": [{
        "id": "V20", "entry": "question_only", "status": "no_leads",
        "discovery": {"leads": [{
            "chunk_id": "one-lead", "source_url": "https://example.org/one",
            "source_revision": "rev-1", "source_license": "CC BY-SA 4.0",
        }]},
    }]}
    pointers = expected_passage_sources(report)
    packet_id = hashlib.sha256(json.dumps(report, sort_keys=True).encode("utf-8")).hexdigest()
    reviews = [
        {"reviewer": reviewer, "packet_id": packet_id,
         "passages": {"V20:discovery:one-lead": "relevant"}, "passage_sources": pointers}
        for reviewer in ("writer-a", "writer-b")
    ]

    summary = aggregate_passage_reviews(report, reviews)

    assert summary["discovery_attempts"] == 1
    assert summary["discovery_insufficient_leads"] == 1
    assert summary["selected_discovery_sets"] == 0
    assert summary["per_task"]["V20"]["discovery_status"] == "insufficient_leads"
