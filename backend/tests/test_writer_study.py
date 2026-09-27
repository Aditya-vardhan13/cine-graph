from collections import Counter
from pathlib import Path

from app.services.writer_study import REVIEW_FIELDS, aggregate_reviews, load_tasks, render_packet, technical_checks


def test_writer_study_fixture_keeps_unsupported_entry_flows_in_scope() -> None:
    manifest = load_tasks(Path(__file__).parent / "fixtures" / "writer-study-v1.json")

    assert len(manifest["tasks"]) == 20
    assert Counter(task["entry"] for task in manifest["tasks"]) == {
        "pair": 16, "film_first": 2, "question_only": 2,
    }
    assert sum(task["category"] == "unanswerable" for task in manifest["tasks"]) >= 2


def test_technical_checks_count_missing_provenance_without_claiming_accuracy() -> None:
    source_card = {
        "chunk_id": "passage-1", "source_url": "https://en.wikipedia.org/wiki/Film",
        "source_revision": "123", "source_license": "CC BY-SA 4.0",
    }
    result = {
        "degraded": False,
        "lenses": [
            {"first_evidence": source_card, "second_evidence": None},
            {"first_evidence": source_card, "second_evidence": {"chunk_id": "passage-2"}},
        ],
    }

    checks = technical_checks(result)

    assert checks["displayed_cards"] == 3
    assert checks["missing_cards"] == 1
    assert checks["cards_without_source_pointer"] == 1
    assert checks["repeated_chunk_ids_by_film"] == {"first": 1, "second": 0}
    assert "accurate" not in checks


def test_review_packet_escapes_source_and_task_text() -> None:
    packet = render_packet({"tasks": [{
        "id": "W19", "category": "plot_structure", "entry": "question_only",
        "question": "<script>alert('x')</script>", "status": "unsupported_entry_flow",
        "reason": "Select <two> films.",
    }]})

    assert "&lt;script&gt;" in packet
    assert "Select &lt;two&gt; films." in packet
    assert "<script>alert('x')</script>" not in packet
    assert "Download my review JSON" in packet


def test_v2_packet_labels_each_source_passage_with_stable_context_and_pointer() -> None:
    source = {
        "chunk_id": "source-123", "section_title": "Plot", "excerpt": "A cited passage",
        "source_url": "https://example.org/story?x=1&y=2", "source_revision": "42",
        "source_license": "CC BY-SA 4.0",
    }
    report = {"version": "writer-study-v2", "tasks": [{
        "id": "V01", "category": "plot_structure", "entry": "question_only",
        "question": "How is the story constructed?", "status": "displayed", "elapsed_ms": 10,
        "discovery": {"method": "lexical", "leads": [
            {**source, "film": {"title": "First"}},
            {**source, "chunk_id": "source-234", "film": {"title": "Second"}},
            {**source, "chunk_id": "source-345", "film": {"title": "Other"}},
        ]},
        "comparison": {
            "first": {"title": "First"}, "second": {"title": "Second"},
            "retrieval_method": "lexical", "lenses": [{
                "identifier": "plot_engine", "label": "Plot engine", "writer_prompt": "Compare them",
                "first_evidence": source, "second_evidence": {**source, "chunk_id": "source-456"},
            }, {
                "identifier": "production", "label": "Production", "writer_prompt": "Optional context",
                "first_evidence": {**source, "chunk_id": "source-567"},
                "second_evidence": {**source, "chunk_id": "source-678"},
            }], "caution": "Context is limited.", "degraded": False,
        },
    }]}

    packet = render_packet(report)

    assert "data-passage='V01:discovery:source-123'" in packet
    assert "data-passage='V01:discovery:source-234'" in packet
    assert "data-passage='V01:discovery:source-345'" not in packet
    assert "data-passage='V01:comparison:plot_engine:first:source-123'" in packet
    assert "data-passage='V01:comparison:plot_engine:second:source-456'" in packet
    assert packet.count("data-passage-source-url='https://example.org/story?x=1&amp;y=2'") == 4
    assert "data-passage='V01:comparison:production:first:source-567'" not in packet
    assert "Additional comparison lenses · optional context" in packet
    assert "data-passage-source-revision='42'" in packet
    assert "<option value='relevant'>Relevant</option>" in packet
    assert "output.passages={}" in packet
    assert "output.passage_sources={}" in packet


def test_v1_packet_does_not_change_review_export_shape() -> None:
    report = {"version": "writer-study-v1", "tasks": [{
        "id": "W01", "category": "plot_structure", "entry": "question_only",
        "question": "How is the story constructed?", "status": "unsupported_entry_flow",
        "reason": "This flow was not yet supported.",
    }]}

    packet = render_packet(report)

    assert "data-passage='" not in packet
    assert "writer-study-v1-review" in packet


def test_product_gate_requires_two_complete_reviews_and_abstention() -> None:
    report = {"version": "writer-study-v1", "tasks": [
        {"id": f"W{number:02d}", "category": "unanswerable" if number == 16 else "craft", "status": "displayed"}
        for number in range(1, 21)
    ]}
    review_tasks = {
        task["id"]: {**dict.fromkeys(REVIEW_FIELDS, "no"), "useful": "yes", "task_seconds": "30"}
        for task in report["tasks"]
    }
    review_tasks["W16"]["abstained_when_needed"] = "yes"
    first = {"version": "writer-study-v1-review", "reviewer": "writer-a", "tasks": review_tasks}
    second = {"version": "writer-study-v1-review", "reviewer": "writer-b", "tasks": review_tasks}

    summary = aggregate_reviews(report, [first, second])

    assert summary["passed"] is True
    assert summary["both_reviewers_useful_count"] == 20
    altered = {**second, "tasks": {**review_tasks, "W16": {**review_tasks["W16"], "abstained_when_needed": "no"}}}
    assert aggregate_reviews(report, [first, altered])["passed"] is False
    unsupported_report = {**report, "tasks": [
        {**task, "status": "unsupported_entry_flow" if task["id"] == "W01" else "displayed"}
        for task in report["tasks"]
    ]}
    assert aggregate_reviews(unsupported_report, [first, second])["both_reviewers_useful_count"] == 19
