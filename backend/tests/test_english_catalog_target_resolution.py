import json

import pytest

from app.services.english_catalog_target import build_english_catalog_target
from app.services.english_catalog_target_resolution import resolve_english_catalog_target


def test_target_resolution_only_returns_exact_title_year_candidates():
    csv_bytes = (
        b"Series_Title,Released_Year\n"
        b"Canon,2001\nAlias,2002\nAmbiguous,2003\nMissing,2004\n"
    )
    target = build_english_catalog_target(csv_bytes, expected_count=4)
    target_bytes = json.dumps(target, sort_keys=True).encode()
    readiness = {"films": [
        {"film_id": "f1", "title": "Canon", "language": "en",
         "release_years_from_resolved_events": ["2001"]},
        {"film_id": "f2", "title": "Canonical Alias Film", "language": "en",
         "aliases": [{"value": "Alias"}], "release_years_from_resolved_events": ["2002"]},
        {"film_id": "f3", "title": "Film Three", "language": "en",
         "aliases": [{"value": "Ambiguous"}], "release_years_from_resolved_events": ["2003"]},
        {"film_id": "f4", "title": "Film Four", "language": "fr",
         "aliases": [{"value": "Ambiguous"}], "release_years_from_resolved_events": ["2003"]},
        {"film_id": "f5", "title": "Canon", "language": "en",
         "release_years_from_resolved_events": ["2002"]},
    ]}
    readiness_bytes = json.dumps(readiness, sort_keys=True).encode()
    report = resolve_english_catalog_target(
        target, readiness, target_bytes=target_bytes, readiness_bytes=readiness_bytes,
    )
    assert report["read_only"] is True
    assert report["identity_candidate_status_counts"] == {
        "ambiguous_exact_alias_year": 1,
        "exact_alias_year_candidate": 1,
        "exact_title_year_candidate": 1,
        "unmatched_exact_title_year": 1,
    }
    assert report["candidates"][0]["catalog_candidates"][0]["film_id"] == "f1"
    assert report["candidates"][1]["catalog_candidates"][0]["matched_alias"] == "Alias"
    assert {item["catalog_language"] for item in report["candidates"][2]["catalog_candidates"]} == {"en", "fr"}
    assert report["candidates"][3]["catalog_candidates"] == []


def test_target_resolution_rejects_inconsistent_target_count():
    csv_bytes = b"Series_Title,Released_Year\nFilm,2001\n"
    target = build_english_catalog_target(csv_bytes, expected_count=1)
    target["candidate_count"] = 2
    with pytest.raises(ValueError, match="inconsistent"):
        resolve_english_catalog_target(
            target, {"films": []}, target_bytes=b"{}", readiness_bytes=b"{}",
        )
