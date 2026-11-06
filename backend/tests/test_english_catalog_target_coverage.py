import pytest
from app.services.english_catalog_target_coverage import (
    build_english_catalog_target_coverage,
    render_english_catalog_target_coverage,
)


def test_target_coverage_keeps_all_mapping_states_and_field_denominators():
    target = {"candidate_count": 4, "candidates": [
        {"selection_rank": 1, "title": "Exact", "release_year_candidate": 2000},
        {"selection_rank": 2, "title": "Linked", "release_year_candidate": 2001},
        {"selection_rank": 3, "title": "Ambiguous", "release_year_candidate": 2002},
        {"selection_rank": 4, "title": "Missing", "release_year_candidate": 2003},
    ]}
    identity = {"candidates": [
        {"selection_rank": 1, "identity_candidate_status": "exact_title_year_candidate",
         "catalog_candidates": [{"film_id": "f1", "catalog_language": "en"}]},
        {"selection_rank": 2, "identity_candidate_status": "unmatched_exact_title_year",
         "catalog_candidates": []},
        {"selection_rank": 3, "identity_candidate_status": "ambiguous_exact_title_year",
         "catalog_candidates": [{"film_id": "f3"}, {"film_id": "f4"}]},
        {"selection_rank": 4, "identity_candidate_status": "unmatched_exact_title_year",
         "catalog_candidates": []},
    ]}
    imdb_review = {"candidates": [
        {"selection_rank": 2, "imdb_candidates": [{
            "title_exact_after_normalization": True, "year_exact": True,
            "catalog_identity_candidates": [{"film_id": "f2"}],
        }]},
        {"selection_rank": 4, "imdb_candidates": []},
    ]}
    readiness = {"films": [
        {"film_id": "f1", "title": "Exact", "language": "en", "release_date": "2000-01-01",
         "runtime_minutes": 100, "narrative_categories": ["plot", "reception"],
         "credits_by_role": {"cast": {"count": 2, "with_character": 1}},
         "source_snapshots": 1, "narrative_use_coverage": {"eligible": 1},
         "embedding_vectors": 5, "semantically_eligible_embedding_vectors": 3,
         "release_years_from_resolved_events": ["2000"]},
        {"film_id": "f2", "title": "Linked", "language": "und",
         "narrative_categories": ["production"], "credits_by_role": {},
         "source_snapshots": 2, "narrative_use_coverage": {"eligible": 0},
         "embedding_vectors": 4, "semantically_eligible_embedding_vectors": 0,
         "release_years_from_resolved_events": []},
    ]}
    report = build_english_catalog_target_coverage(target, identity, imdb_review, readiness)
    assert report["target_count"] == 4
    assert report["catalog_candidate_mappings"] == 2
    assert report["mapping_status_counts"] == {
        "ambiguous_catalog_candidates": 1,
        "candidate_review_required": 2,
        "no_catalog_candidate": 1,
    }
    assert report["mapped_candidate_language_counts"] == {"en": 1, "und": 1}
    assert report["mapped_candidate_category_counts"]["plot"] == 1
    assert report["mapped_candidate_counts"]["with_any_eligible_embedding"] == 1
    assert report["mapped_candidate_counts"]["with_resolved_character_assertion"] == 0
    markdown = render_english_catalog_target_coverage(report)
    assert "not certified as an English-only set" in markdown
    assert "2 mapped candidates" in markdown


def test_target_coverage_rejects_incomplete_identity_audit():
    with pytest.raises(ValueError, match="every target rank"):
        build_english_catalog_target_coverage(
            {"candidate_count": 1, "candidates": [{"selection_rank": 1}]},
            {"candidates": []}, {"candidates": []}, {"films": []},
        )
