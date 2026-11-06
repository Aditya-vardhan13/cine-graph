import pytest

from app.services.english_catalog_pilot_reconciliation import (
    EnglishPilotReconciliationError,
    reconcile_english_pilot_captures,
    render_reconciliation_markdown,
)


def _pilot() -> dict:
    return {
        "version": "english-catalog-pilot-v1",
        "selection_sha256": "p" * 64,
        "film_count": 2,
        "films": [
            {"selection_rank": rank, "input_title": f"Film {rank}", "input_year": 2000 + rank,
             "wikidata_id": f"Q{rank}", "catalog_film_id": f"film-{rank}",
             "catalog_language": "en", "catalog_match": "exact_title_year"}
            for rank in (1, 2)
        ],
    }


def _bundle(rank: int, *, selection_hash: str, missing_plot: bool = False) -> tuple[str, dict, dict]:
    title, year, qid = f"Film {rank}", 2000 + rank, f"Q{rank}"
    categories = {key: 1 for key in ("plot", "production", "reception", "themes_analysis", "legacy")}
    if missing_plot:
        categories["plot"] = 0
    metadata = {
        "value_statement_counts": {"cast": 2, "release_date": 1, "runtime": 1},
        "cast_with_character_qualifier": 1,
        "cast_without_character_qualifier": 1,
        "release_dates_with_territory": 1,
        "release_dates_with_references": 1,
    }
    capture = {
        "schema": "cinegraph.catalog-pilot-capture/v1",
        "selection_sha256": selection_hash,
        "run_status": "complete",
        "films": [{"selection_rank": rank, "title": title, "year": year, "qid": qid,
                   "identity_status": "verified", "wikipedia_status": "captured",
                   "wikipedia_sha256": "w" * 64, "wikidata_sha256": "d" * 64}],
    }
    audit = {
        "schema": "cinegraph.catalog-pilot-audit/v2",
        "selection_sha256": selection_hash,
        "identity_and_capture_pass": True,
        "audited_films": 1,
        "requested_films": 1,
        "films": [{"title": title, "year": year, "qid": qid,
                   "wikipedia_revision": rank, "wikidata_revision": rank,
                   "passage_count": 4, "categories": categories,
                   "wikidata_metadata": metadata,
                   "missing_content_categories": ["plot"] if missing_plot else []}],
        "total_passages": 4,
        "total_raw_capture_bytes": 1000,
        "passages_with_citation_markers": 3,
    }
    return f"rank {rank}", capture, audit


def test_reconciles_distinct_manifest_hashes_only_with_exact_pilot_rows() -> None:
    report = reconcile_english_pilot_captures(
        _pilot(), [_bundle(1, selection_hash="o" * 64), _bundle(2, selection_hash="p" * 64)],
        pilot_sha256="p" * 64,
    )

    assert report["captured_films"] == 2
    assert report["exact_rank_title_year_qid_match"] is True
    assert report["batches"][0]["selection_hash_matches_pilot"] is False
    assert report["batches"][1]["selection_hash_matches_pilot"] is True
    assert report["passages"] == 8
    assert report["wikidata_metadata"]["cast_statements"] == 4
    assert report["cast_credits_with_character_qualifier"] == 2
    assert report["content_coverage"]["plot"]["films_missing_section"] == 0
    assert "exact row reconciliation used" in render_reconciliation_markdown(report)


def test_reports_missing_plot_as_a_content_gap_not_capture_failure() -> None:
    report = reconcile_english_pilot_captures(
        _pilot(), [_bundle(1, selection_hash="p" * 64, missing_plot=True),
                   _bundle(2, selection_hash="p" * 64)],
        pilot_sha256="p" * 64,
    )

    assert report["all_sources_passed_integrity_audit"] is True
    assert report["content_coverage"]["plot"]["films_missing_section"] == 1
    assert report["content_gaps"][0]["qid"] == "Q1"


def test_rejects_missing_or_mismatched_capture_ranks() -> None:
    with pytest.raises(EnglishPilotReconciliationError, match="do not cover pilot ranks"):
        reconcile_english_pilot_captures(
            _pilot(), [_bundle(1, selection_hash="p" * 64)], pilot_sha256="p" * 64,
        )

    wrong = _bundle(2, selection_hash="p" * 64)
    wrong[1]["films"][0]["title"] = "Wrong Film"
    with pytest.raises(EnglishPilotReconciliationError, match="does not uniquely match"):
        reconcile_english_pilot_captures(
            _pilot(), [_bundle(1, selection_hash="p" * 64), wrong], pilot_sha256="p" * 64,
        )


def test_rejects_a_failed_source_integrity_audit() -> None:
    bundle = _bundle(1, selection_hash="p" * 64)
    bundle[2]["identity_and_capture_pass"] = False
    with pytest.raises(EnglishPilotReconciliationError, match="integrity audit did not pass"):
        reconcile_english_pilot_captures(
            _pilot(), [bundle, _bundle(2, selection_hash="p" * 64)], pilot_sha256="p" * 64,
        )


def test_rejects_duplicate_work_identity_in_the_frozen_manifest() -> None:
    pilot = _pilot()
    pilot["films"][1]["wikidata_id"] = pilot["films"][0]["wikidata_id"]
    with pytest.raises(EnglishPilotReconciliationError, match="unique exact English catalog identity"):
        reconcile_english_pilot_captures(
            pilot,
            [_bundle(1, selection_hash="p" * 64), _bundle(2, selection_hash="p" * 64)],
            pilot_sha256="p" * 64,
        )
