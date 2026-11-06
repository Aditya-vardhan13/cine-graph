import pytest

from app.services.english_catalog_imdb_review import build_imdb_identity_review


def test_imdb_results_are_review_leads_only_and_crosslinked_by_external_id():
    identity = {
        "schema": "cinegraph.english-catalog-target-identity-audit/v1",
        "candidates": [
            {"selection_rank": 5, "input_title": "Film", "input_year": 2000,
             "identity_candidate_status": "unmatched_exact_title_year"},
            {"selection_rank": 8, "input_title": "Unknown", "input_year": 2001,
             "identity_candidate_status": "ambiguous_exact_title_year"},
        ],
    }
    readiness = {"films": [{"film_id": "film-1", "title": "Film", "wikidata_id": "Q1",
                             "resolved_imdb_ids": ["tt0000001"]}]}
    report = build_imdb_identity_review(identity, readiness, {
        5: [{"tconst": "tt0000001", "title": "Film", "year": 2000, "score": 1.0}],
        8: [{"tconst": "tt0000002", "title": "Unknown Movie", "year": 2001, "score": 0.9}],
    })
    assert report["read_only"] is True
    assert report["review_queue_count"] == 2
    assert report["candidate_status_counts"] == {
        "no_exact_imdb_title_year_candidate": 1,
        "unique_exact_imdb_crosslink_candidate_review_required": 1,
    }
    first = report["candidates"][0]
    assert first["review_status"] == "review_required"
    assert first["imdb_candidates"][0]["catalog_identity_candidates"][0]["wikidata_id"] == "Q1"
    assert "non-commercial" in report["source_policy"]


def test_imdb_review_rejects_invalid_candidates_and_out_of_scope_ranks():
    identity = {"schema": "cinegraph.english-catalog-target-identity-audit/v1",
                "candidates": [{"selection_rank": 1, "input_title": "Film", "input_year": 2000,
                                "identity_candidate_status": "unmatched_exact_title_year"}]}
    with pytest.raises(ValueError, match="invalid title ID"):
        build_imdb_identity_review(identity, {"films": []}, {1: [{"tconst": "not-an-id"}]})
    with pytest.raises(ValueError, match="outside the review queue"):
        build_imdb_identity_review(identity, {"films": []}, {2: []})
