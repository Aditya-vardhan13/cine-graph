import json

import pytest

from app.services.english_catalog_pilot import (
    build_english_catalog_pilot,
    validate_english_catalog_pilot,
)


def artifacts():
    csv_bytes = (
        b"Series_Title,Released_Year\n"
        b"Non-English,2000\n"
        b"Canonical,2001\n"
        b"No Match,2002\n"
        b"Alias,2003\n"
        b"Ambiguous,2004\n"
        b"Duplicate,2005\n"
        b"Third,2006\n"
    )
    readiness = {
        "films": [
            {"film_id": "film-fr", "title": "Non-English", "language": "fr",
             "release_years_from_resolved_events": ["2000"]},
            {"film_id": "film-1", "title": "Canonical", "language": "en",
             "release_years_from_resolved_events": ["2001"], "gaps": ["runtime"]},
            {"film_id": "film-2", "title": "Actual Title", "language": "en",
             "aliases": [{"value": "Alias"}], "release_years_from_resolved_events": ["2003"]},
            {"film_id": "film-3", "title": "Ambiguous A", "language": "en",
             "aliases": [{"value": "Ambiguous"}], "release_years_from_resolved_events": ["2004"]},
            {"film_id": "film-4", "title": "Ambiguous B", "language": "en",
             "aliases": [{"value": "Ambiguous"}], "release_years_from_resolved_events": ["2004"]},
            {"film_id": "film-1", "title": "Duplicate", "language": "en",
             "release_years_from_resolved_events": ["2005"]},
            {"film_id": "film-5", "title": "Third", "language": "en",
             "release_years_from_resolved_events": ["2006"]},
        ]
    }
    readiness_bytes = json.dumps(readiness, separators=(",", ":")).encode()
    return csv_bytes, readiness_bytes


def test_english_pilot_selects_unique_exact_and_alias_matches_only():
    csv_bytes, readiness_bytes = artifacts()
    pilot = build_english_catalog_pilot(csv_bytes, readiness_bytes, expected_count=2)
    assert pilot["film_count"] == 2
    assert pilot["input_rows_scanned"] == 4
    assert [item["input_rank"] for item in pilot["films"]] == [2, 4]
    assert [item["catalog_match"] for item in pilot["films"]] == [
        "exact_title_year", "exact_alias_year",
    ]
    assert pilot["films"][1]["catalog_title"] == "Actual Title"
    assert pilot["films"][0]["gaps"] == ["runtime"]


def test_english_pilot_skips_nonenglish_unmatched_ambiguous_and_duplicate_rows():
    csv_bytes, readiness_bytes = artifacts()
    pilot = build_english_catalog_pilot(csv_bytes, readiness_bytes, expected_count=3)
    assert pilot["input_rows_scanned"] == 7
    assert pilot["skipped_input_rows_before_completion"] == {
        "ambiguous_english_title_year": 1,
        "duplicate_catalog_film": 1,
        "no_exact_title_year_match": 1,
        "non_english_or_unclassified_match": 1,
    }


def test_english_pilot_rejects_changed_or_nonreproducible_manifest():
    csv_bytes, readiness_bytes = artifacts()
    pilot = build_english_catalog_pilot(csv_bytes, readiness_bytes, expected_count=2)
    assert validate_english_catalog_pilot(
        pilot, csv_bytes, readiness_bytes, expected_count=2,
    )["valid"]
    changed = json.loads(json.dumps(pilot))
    changed["films"][0]["catalog_language"] = "fr"
    with pytest.raises(ValueError, match="deterministic selection"):
        validate_english_catalog_pilot(changed, csv_bytes, readiness_bytes, expected_count=2)


def test_english_pilot_fails_if_requested_count_is_not_available():
    csv_bytes, readiness_bytes = artifacts()
    with pytest.raises(ValueError, match="Only 3 unique"):
        build_english_catalog_pilot(csv_bytes, readiness_bytes, expected_count=4)
