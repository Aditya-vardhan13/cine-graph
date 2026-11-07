from app.services.wikipedia_cast_candidate_source_audit import (
    candidate_audit_summary,
    passage_binding_errors,
    sha256,
)


def test_candidate_phrase_must_match_exact_article_revision_and_section_passage():
    film = {
        "qid": "Q10", "selection_rank": 1, "title": "Example Film", "year": 2001,
        "wikipedia_attribution_url": "https://en.wikipedia.org/wiki/Example_Film",
        "wikipedia_revision": 123, "wikipedia_sha256": "a" * 64, "wikipedia_license": "CC BY-SA 4.0",
    }
    passage = {
        "section_locator": "cast", "section_title": "Cast", "ordinal": 0,
        "content": "Actor Example as Character Example",
        "content_sha256": "",
    }
    passage["content_sha256"] = sha256(passage["content"].encode())
    candidate = {
        "film_qid": "Q10", "selection_rank": 1, "film_title": "Example Film", "film_year": 2001,
        "wikipedia_url": film["wikipedia_attribution_url"], "wikipedia_revision": 123,
        "wikipedia_snapshot_sha256": "a" * 64, "wikipedia_license": "CC BY-SA 4.0",
        "section_locator": "cast", "section_title": "Cast", "passage_ordinal": 0,
        "passage_sha256": passage["content_sha256"], "evidence_phrase": "Actor Example as Character Example",
    }
    assert passage_binding_errors(candidate, film, passage) == []


def test_candidate_phrase_and_source_identity_fail_closed_on_mismatch():
    film = {
        "qid": "Q10", "selection_rank": 1, "title": "Example Film", "year": 2001,
        "wikipedia_attribution_url": "https://en.wikipedia.org/wiki/Example_Film",
        "wikipedia_revision": 123, "wikipedia_sha256": "a" * 64, "wikipedia_license": "CC BY-SA 4.0",
    }
    passage = {
        "section_locator": "plot", "section_title": "Plot", "ordinal": 0,
        "content": "A passage about the plot.",
        "content_sha256": "3d0e8a4f3f2d3f17b609a2f1f6d1e98f9a4c60f30b5b0b1538fca5c6a6f36cf3",
    }
    candidate = {
        "film_qid": "Q11", "selection_rank": 2, "film_title": "Other Film", "film_year": 2002,
        "wikipedia_url": "https://en.wikipedia.org/wiki/Other_Film", "wikipedia_revision": 456,
        "wikipedia_snapshot_sha256": "b" * 64, "wikipedia_license": "CC BY-SA 4.0",
        "section_locator": "cast", "section_title": "Cast", "passage_ordinal": 1,
        "passage_sha256": "c" * 64, "evidence_phrase": "Invented Actor as Character",
    }
    errors = passage_binding_errors(candidate, film, passage)
    assert "film_qid_mismatch" in errors
    assert "article_revision_mismatch" in errors
    assert "passage_section_mismatch" in errors
    assert "evidence_phrase_not_in_passage" in errors


def test_audit_summary_is_explicitly_not_a_credit_truth_score():
    summary = candidate_audit_summary(
        capture_manifest_sha256="a" * 64,
        candidate_report_sha256="b" * 64,
        films=1,
        snapshots_verified=1,
        passage_derivatives_verified=1,
        candidate_rows=2,
        candidate_rows_verified=2,
        quarantined_rows=1,
        quarantined_rows_verified=1,
        error_counts={},
    )
    assert summary["status"] == "passed"
    assert summary["candidate_source_bindings_verified"] == 2
    assert "source_phrase_truth_claimed" not in summary


def test_exact_phrase_in_a_non_cast_section_is_not_a_cast_candidate():
    film = {
        "qid": "Q10", "selection_rank": 1, "title": "Example Film", "year": 2001,
        "wikipedia_attribution_url": "https://en.wikipedia.org/wiki/Example_Film",
        "wikipedia_revision": 123, "wikipedia_sha256": "a" * 64, "wikipedia_license": "CC BY-SA 4.0",
    }
    content = "Actor Example as Character Example"
    passage = {
        "section_locator": "plot", "section_title": "Plot", "ordinal": 0,
        "content": content, "content_sha256": sha256(content.encode()),
    }
    candidate = {
        "film_qid": "Q10", "selection_rank": 1, "film_title": "Example Film", "film_year": 2001,
        "wikipedia_url": film["wikipedia_attribution_url"], "wikipedia_revision": 123,
        "wikipedia_snapshot_sha256": "a" * 64, "wikipedia_license": "CC BY-SA 4.0",
        "section_locator": "plot", "section_title": "Plot", "passage_ordinal": 0,
        "passage_sha256": passage["content_sha256"], "evidence_phrase": content,
    }
    assert passage_binding_errors(candidate, film, passage) == ["candidate_outside_cast_section"]
