import pytest

from scripts.render_catalog_pilot_coverage import build_coverage_rows, render_markdown


def sample_reports():
    pilot = {"film_count": 100, "films": []}
    readiness = {"database_read_only": True, "films": []}
    metadata = {"database_read_only": True, "pilot_sha256": "pilot-hash", "films": []}
    for rank in range(1, 101):
        film_id = f"film-{rank}"
        qid = f"Q{rank}"
        pilot["films"].append({
            "selection_rank": rank,
            "input_title": f"Film {rank}",
            "input_year": 2000 + rank,
            "match_status": "exact_title_year",
            "catalog_candidates": [{"film_id": film_id, "wikidata_id": qid}],
        })
        readiness["films"].append({
            "film_id": film_id,
            "wikidata_id": qid,
            "title": f"Film {rank}",
            "language": "en",
            "narrative_categories": ["plot"],
            "resolved_assertions": {"director": 1, "cast": 5, "character": 2},
            "narrative_use_coverage": {
                "total": 1, "with_license_and_attribution": 1,
                "approved": 0, "eligible": 0,
            },
            "embedding_vectors": 3,
            "semantically_eligible_embedding_vectors": 0,
        })
        metadata["films"].append({
            "film_id": film_id,
            "wikidata_id": qid,
            "release_profile_status": "legacy_date_missing",
            "legacy_profile": {"release_date": None, "runtime_minutes": None},
            "default_display_research_projection": {
                "release_date": "2001-01-01", "release_year": 2001,
                "runtime_options": [{"minutes": 120}],
            },
            "runtime_profile_status": "eligible_runtime_missing_from_legacy_profile",
        })
    return pilot, readiness, metadata


def sample_identity_decisions(pilot):
    return {
        "scope": "pilot membership only; no catalog identity merge and no IMDb field reuse",
        "input_sha256": {"pilot": "pilot-hash"},
        "decision_count": 1,
        "decisions": [{
            "selection_rank": 1,
            "input_title": pilot["films"][0]["input_title"],
            "input_year": pilot["films"][0]["input_year"],
            "film_id": "film-1",
            "wikidata_id": "Q1",
            "decision": "accepted_same_work_for_pilot_membership_only",
            "operational_identity_merged": False,
            "source_fields_authorized_for_product": False,
        }],
    }


def test_pilot_coverage_sheet_joins_only_matching_source_identity() -> None:
    pilot, readiness, metadata = sample_reports()
    rows = build_coverage_rows(pilot, readiness, metadata, pilot_sha256="pilot-hash")
    assert len(rows) == 100
    assert rows[0]["narrative"] == {"snapshots": 1, "with_license_attribution": 1, "approved": 0, "eligible": 0}
    assert rows[0]["vectors"] == {"stored": 3, "eligible": 0}
    report = render_markdown(
        rows, readiness, {**metadata, "generated_at": "2026-11-06T00:00:00+00:00",
                          "snapshot_integrity": {"unique_snapshot_status_counts": {"verified": 1},
                                                 "evidence_references_without_snapshot": 0}},
        pilot_sha256="pilot-hash", readiness_sha256="readiness-hash", metadata_sha256="metadata-hash",
    )
    assert "| 1 | Film 1 (2001) | en | `exact title year`" in report
    assert "Narrative snapshots: **100**" in report
    assert "vectors eligible under current rights policy: **0**" in report


def test_pilot_coverage_sheet_rejects_mixed_identity_or_pilot_hash() -> None:
    pilot, readiness, metadata = sample_reports()
    readiness["films"][0]["wikidata_id"] = "Q-mismatch"
    with pytest.raises(ValueError, match="Source identity mismatch"):
        build_coverage_rows(pilot, readiness, metadata, pilot_sha256="pilot-hash")
    pilot, readiness, metadata = sample_reports()
    with pytest.raises(ValueError, match="exact pilot bytes"):
        build_coverage_rows(pilot, readiness, {**metadata, "pilot_sha256": "other"}, pilot_sha256="pilot-hash")


def test_crosslink_is_labeled_membership_only_and_shows_both_titles() -> None:
    pilot, readiness, metadata = sample_reports()
    item = pilot["films"][0]
    item.update({"input_title": "Gisaengchung", "input_year": 2019,
                 "match_status": "review_required_unique_imdb_crosslink"})
    readiness["films"][0]["title"] = "Parasite"
    decisions = sample_identity_decisions(pilot)
    rows = build_coverage_rows(
        pilot, readiness, metadata, pilot_sha256="pilot-hash", identity_decisions=decisions,
    )
    assert rows[0]["identity"] == "crosslink: pilot membership only"
    report = render_markdown(
        rows, readiness,
        {**metadata, "snapshot_integrity": {"unique_snapshot_status_counts": {},
                                            "evidence_references_without_snapshot": 0}},
        pilot_sha256="pilot-hash", readiness_sha256="readiness-hash", metadata_sha256="metadata-hash",
    )
    assert "Gisaengchung (2019) → Parasite" in report
    assert "crosslink: pilot membership only" in report
    assert "not a catalog identity merge" in report


def test_crosslink_decision_rejects_product_authorization_or_wrong_film() -> None:
    pilot, readiness, metadata = sample_reports()
    pilot["films"][0]["match_status"] = "review_required_unique_imdb_crosslink"
    decisions = sample_identity_decisions(pilot)
    decisions["decisions"][0]["source_fields_authorized_for_product"] = True
    with pytest.raises(ValueError, match="selection-only"):
        build_coverage_rows(
            pilot, readiness, metadata, pilot_sha256="pilot-hash", identity_decisions=decisions,
        )
    decisions = sample_identity_decisions(pilot)
    decisions["decisions"][0]["film_id"] = "wrong-film"
    with pytest.raises(ValueError, match="does not match pilot rank"):
        build_coverage_rows(
            pilot, readiness, metadata, pilot_sha256="pilot-hash", identity_decisions=decisions,
        )
