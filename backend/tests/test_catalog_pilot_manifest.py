import hashlib
import json

import pytest

from app.services.catalog_pilot_manifest import (
    adjudicate_pilot_crosslinks, validate_pilot_manifest,
)


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


def crosslink_adjudication_artifacts():
    pilot = {"version": "catalog-pilot-top100-v5", "imdb_review_sha256": "",
             "films": [{"selection_rank": 1, "input_title": "Example (original title)",
                        "input_year": 2001, "match_status": "review_required_unique_imdb_crosslink",
                        "catalog_candidates": [{"film_id": "film-1", "title": "Example",
                                                "wikidata_id": "Q123", "imdb_id": "tt0000001",
                                                "review_required": True}]}]}
    pilot_bytes = json.dumps(pilot, separators=(",", ":")).encode()
    review = {"candidates": [{"selection_rank": 1, "imdb_candidates": [{
        "tconst": "tt0000001", "title": "Example (original title)", "year": 2001,
        "score": 1.0, "title_year_match": True,
        "catalog_identity_candidates": [{"film_id": "film-1", "title": "Example", "wikidata_id": "Q123"}],
    }]}]}
    review_bytes = json.dumps(review, separators=(",", ":")).encode()
    pilot["imdb_review_sha256"] = hashlib.sha256(review_bytes).hexdigest()
    pilot_bytes = json.dumps(pilot, separators=(",", ":")).encode()
    evidence = {"pilot_sha256": hashlib.sha256(pilot_bytes).hexdigest(), "crosslinks": 1,
                "candidates": [{"selection_rank": 1, "input_title": "Example (original title)",
                    "input_year": 2001, "film_id": "film-1", "catalog_title": "Example",
                    "wikidata_id": "Q123", "imdb_id": "tt0000001",
                    "evidence_status": "resolved_wikidata_p345", "evidence": [{
                        "assertion_id": "assertion-1", "source_assertion_id": "source-assertion-1",
                        "source_revision": "12345", "source": "Wikidata",
                        "source_property": "P345", "raw_value_matches": True,
                        "review_status": "resolved", "license": "CC0 1.0",
                        "attributed": True, "source_url": "https://www.wikidata.org/wiki/Q123",
                    }]}]}
    evidence_bytes = json.dumps(evidence, separators=(",", ":")).encode()
    return pilot, pilot_bytes, review, review_bytes, evidence, evidence_bytes


def test_crosslink_decisions_are_explicitly_limited_to_pilot_membership():
    artifacts = crosslink_adjudication_artifacts()
    result = adjudicate_pilot_crosslinks(*artifacts)
    decision = result["decisions"][0]
    assert result["decision_count"] == 1
    assert decision["decision"] == "accepted_same_work_for_pilot_membership_only"
    assert decision["operational_identity_merged"] is False
    assert decision["source_fields_authorized_for_product"] is False
    assert "no catalog identity merge" in result["scope"]


def test_crosslink_adjudication_fails_closed_without_matching_p345_evidence():
    artifacts = list(crosslink_adjudication_artifacts())
    artifacts[4]["candidates"][0]["evidence"] = []
    artifacts[5] = json.dumps(artifacts[4], separators=(",", ":")).encode()
    with pytest.raises(ValueError, match="no eligible, matching P345"):
        adjudicate_pilot_crosslinks(*artifacts)


def test_crosslink_adjudication_requires_matching_title_and_year():
    artifacts = list(crosslink_adjudication_artifacts())
    artifacts[2]["candidates"][0]["imdb_candidates"][0]["year"] = 2002
    artifacts[3] = json.dumps(artifacts[2], separators=(",", ":")).encode()
    artifacts[0]["imdb_review_sha256"] = hashlib.sha256(artifacts[3]).hexdigest()
    artifacts[1] = json.dumps(artifacts[0], separators=(",", ":")).encode()
    artifacts[4]["pilot_sha256"] = hashlib.sha256(artifacts[1]).hexdigest()
    artifacts[5] = json.dumps(artifacts[4], separators=(",", ":")).encode()
    with pytest.raises(ValueError, match="title/year IMDb candidate"):
        adjudicate_pilot_crosslinks(*artifacts)


def test_crosslink_adjudication_rejects_weak_title_match_even_with_id_link():
    artifacts = list(crosslink_adjudication_artifacts())
    artifacts[2]["candidates"][0]["imdb_candidates"][0]["score"] = 0.79
    artifacts[3] = json.dumps(artifacts[2], separators=(",", ":")).encode()
    artifacts[0]["imdb_review_sha256"] = hashlib.sha256(artifacts[3]).hexdigest()
    artifacts[1] = json.dumps(artifacts[0], separators=(",", ":")).encode()
    artifacts[4]["pilot_sha256"] = hashlib.sha256(artifacts[1]).hexdigest()
    artifacts[5] = json.dumps(artifacts[4], separators=(",", ":")).encode()
    with pytest.raises(ValueError, match="sufficiently strong"):
        adjudicate_pilot_crosslinks(*artifacts)
