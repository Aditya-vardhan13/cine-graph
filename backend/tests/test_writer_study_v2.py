from collections import Counter
from pathlib import Path

from app.services.writer_study import render_packet, technical_checks
from app.services.writer_study_v2 import load_tasks


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
