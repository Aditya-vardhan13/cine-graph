import pytest

from scripts.render_english_catalog_pilot_coverage import build_rows, render_markdown


def sample_reports():
    pilot = {"film_count": 100, "films": []}
    readiness = {"database_read_only": True, "films": []}
    for rank in range(1, 101):
        film_id = f"film-{rank}"
        qid = f"Q{rank}"
        pilot["films"].append({
            "selection_rank": rank,
            "input_rank": rank + 10,
            "input_title": f"Film {rank}",
            "input_year": 2000 + rank,
            "catalog_match": "exact_title_year",
            "catalog_film_id": film_id,
            "catalog_title": f"Film {rank}",
            "wikidata_id": qid,
            "catalog_language": "en",
        })
        readiness["films"].append({
            "film_id": film_id,
            "wikidata_id": qid,
            "title": f"Film {rank}",
            "language": "en",
            "identity_status": "linked",
            "release_years_from_resolved_events": [str(2000 + rank)],
            "runtime_minutes": None,
            "resolved_assertions": {"director": 1, "writer": 2, "cast": 6, "character": 1},
            "narrative_categories": ["plot", "production"],
            "source_versions": ["fixture-v1"],
            "narrative_use_coverage": {
                "total": 2, "with_license_and_attribution": 2,
                "with_decision": 1, "approved": 0, "denied": 0,
                "review_required": 1, "eligible": 0,
            },
            "embedding_vectors": 3,
            "semantically_eligible_embedding_vectors": 0,
            "gaps": ["runtime_minutes", "semantically_eligible_indexed"],
        })
    return pilot, readiness


def test_english_coverage_sheet_exposes_per_film_gaps_and_rights_state():
    pilot, readiness = sample_reports()
    rows = build_rows(pilot, readiness)
    assert len(rows) == 100
    assert rows[0]["resolved_assertions"] == {"director": 1, "writer": 2, "cast": 6, "character": 1}
    assert rows[0]["snapshots"]["eligible"] == 0
    assert rows[0]["vectors"] == {"stored": 3, "eligible": 0}
    report = render_markdown(rows, pilot_sha256="pilot-hash", readiness_sha256="readiness-hash")
    assert "all selected from unique exact title/year catalog matches classified `en`" in report
    assert "2/2/0/0" in report
    assert "runtime_minutes, semantically_eligible_indexed" in report
    assert "Q1" in report


@pytest.mark.parametrize("mutation, message", [
    ("wrong_manifest_language", "not English-classified"),
    ("wrong_readiness_language", "Readiness language mismatch"),
    ("wrong_qid", "Wikidata identity mismatch"),
    ("duplicate_id", "must be unique strings"),
])
def test_english_coverage_sheet_rejects_scope_or_identity_mismatch(mutation, message):
    pilot, readiness = sample_reports()
    if mutation == "wrong_manifest_language":
        pilot["films"][0]["catalog_language"] = "und"
    elif mutation == "wrong_readiness_language":
        readiness["films"][0]["language"] = "und"
    elif mutation == "wrong_qid":
        readiness["films"][0]["wikidata_id"] = "Q-wrong"
    else:
        pilot["films"][1]["catalog_film_id"] = pilot["films"][0]["catalog_film_id"]
    with pytest.raises(ValueError, match=message):
        build_rows(pilot, readiness)


def test_english_coverage_sheet_requires_read_only_snapshot():
    pilot, readiness = sample_reports()
    readiness["database_read_only"] = False
    with pytest.raises(ValueError, match="database_read_only"):
        build_rows(pilot, readiness)
