import hashlib
import json

import pytest

from app.services.catalog_pilot_manifest import validate_pilot_manifest


def make_artifacts():
    csv_bytes = b"Series_Title,Released_Year\nExample,2001\nAlias,2002\n"
    readiness = {"films": []}
    readiness_bytes = json.dumps(readiness, separators=(",", ":")).encode()
    review = {"candidates": [{"selection_rank": 2, "imdb_candidates": [{
        "tconst": "tt0000002", "title_year_match": True,
        "catalog_identity_candidates": [{"film_id": "film-2", "title": "Alias"}],
    }]}]}
    review_bytes = json.dumps(review, separators=(",", ":")).encode()
    rows = [
        {"selection_rank": 1, "input_title": "Example", "input_year": 2001,
         "match_status": "exact_title_year",
         "catalog_candidates": [{"film_id": "film-1", "release_years_from_resolved_events": ["2001"]}]},
        {"selection_rank": 2, "input_title": "Alias", "input_year": 2002,
         "match_status": "review_required_unique_imdb_crosslink",
         "catalog_candidates": [{"film_id": "film-2", "review_required": True,
                                  "imdb_id": "tt0000002", "identity_evidence": "Wikidata P345"}]},
    ]
    counts = {"exact_title_year": 1, "review_required_unique_imdb_crosslink": 1}
    pilot = {"version": "catalog-pilot-top100-v5", "candidate_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
             "readiness_report_sha256": hashlib.sha256(readiness_bytes).hexdigest(),
             "imdb_review_sha256": hashlib.sha256(review_bytes).hexdigest(), "film_count": 2,
             "match_counts": counts, "films": rows}
    return pilot, csv_bytes, readiness_bytes, review_bytes


def test_manifest_reproduces_row_hashes_and_keeps_crosslink_review_required():
    pilot, csv_bytes, readiness_bytes, review_bytes = make_artifacts()
    result = validate_pilot_manifest(pilot, csv_bytes, readiness_bytes, review_bytes, expected_count=2)
    assert result["valid"] is True
    assert result["identity_state_counts"] == {
        "exact_title_year": 1,
        "review_required_unique_imdb_crosslink": 1,
    }
    assert "does not prove identity truth" in result["caution"]


@pytest.mark.parametrize("artifact", ["csv", "readiness", "review"])
def test_manifest_rejects_changed_input_fingerprints(artifact):
    pilot, csv_bytes, readiness_bytes, review_bytes = make_artifacts()
    if artifact == "csv":
        csv_bytes += b"changed"
    elif artifact == "readiness":
        readiness_bytes += b"changed"
    else:
        review_bytes += b"changed"
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_pilot_manifest(pilot, csv_bytes, readiness_bytes, review_bytes, expected_count=2)


def test_manifest_rejects_crosslink_promoted_without_review_state():
    pilot, csv_bytes, readiness_bytes, review_bytes = make_artifacts()
    pilot["films"][1]["catalog_candidates"][0]["review_required"] = False
    with pytest.raises(ValueError, match="uniquely review-required"):
        validate_pilot_manifest(pilot, csv_bytes, readiness_bytes, review_bytes, expected_count=2)


def test_manifest_rejects_crosslink_not_supported_by_its_review_artifact():
    pilot, csv_bytes, readiness_bytes, review_bytes = make_artifacts()
    review = json.loads(review_bytes)
    review["candidates"][0]["imdb_candidates"][0]["catalog_identity_candidates"] = []
    review_bytes = json.dumps(review, separators=(",", ":")).encode()
    pilot["imdb_review_sha256"] = hashlib.sha256(review_bytes).hexdigest()
    with pytest.raises(ValueError, match="not uniquely supported"):
        validate_pilot_manifest(pilot, csv_bytes, readiness_bytes, review_bytes, expected_count=2)


def test_manifest_rejects_count_or_title_drift():
    pilot, csv_bytes, readiness_bytes, review_bytes = make_artifacts()
    pilot["films"][0]["input_title"] = "Different film"
    with pytest.raises(ValueError, match="does not match the frozen CSV"):
        validate_pilot_manifest(pilot, csv_bytes, readiness_bytes, review_bytes, expected_count=2)
    pilot, csv_bytes, readiness_bytes, review_bytes = make_artifacts()
    with pytest.raises(ValueError, match="exactly 100 rows"):
        validate_pilot_manifest(pilot, csv_bytes, readiness_bytes, review_bytes, expected_count=100)
