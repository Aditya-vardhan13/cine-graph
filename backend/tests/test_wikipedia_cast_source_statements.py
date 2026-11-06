import hashlib
import json

import pytest

from app.services.wikipedia_cast_source_statements import build_source_statement_manifest
from app.services.wikipedia_cast_statement_replay import validate_cast_source_statement_draft


ACTOR_SNAPSHOT_BYTES = json.dumps({"entities": {"Q20": {
    "id": "Q20", "lastrevid": 98765,
    "labels": {"en": {"language": "en", "value": "Actor Name"}},
}}}, sort_keys=True).encode()


def _candidate(**updates):
    row = {
        "film_qid": "Q10",
        "actor_qid": "Q20",
        "actor_identity_qid": "Q20",
        "identity_resolution": "same_film_wikidata_cast_target",
        "actor_identity_match": "same_film_wikidata_cast_target",
        "actor_label": "Actor Name",
        "actor_label_in_source": "Actor Name",
        "actor_identity_label": "Actor Name",
        "actor_identity_evidence": {
            "source_url": "https://www.wikidata.org/wiki/Special:EntityData/Q20.json",
            "source_revision": 98765,
            "snapshot_sha256": hashlib.sha256(ACTOR_SNAPSHOT_BYTES).hexdigest(),
        },
        "actor_statement_locators": ["claims.P161[0]"],
        "character_name_in_source": "Character",
        "evidence_phrase": "Actor Name as Character in the cast list.",
        "section_locator": "cast",
        "passage_ordinal": 2,
        "passage_sha256": "a" * 64,
        "wikipedia_revision": 12345,
        "wikipedia_snapshot_sha256": "b" * 64,
        "wikipedia_url": "https://en.wikipedia.org/wiki/Example_film",
        "wikipedia_license": "CC BY-SA 4.0",
        "matching_wikidata_character_qids": ["Q30"],
        "review_status": "review_required",
    }
    row.update(updates)
    return row


def _build(*candidates, actor_snapshot_override=None):
    report = {
        "schema": "cinegraph.wikipedia-cast-candidates/v7",
        "selection_sha256": "c" * 64,
        "films": [{"film_qid": "Q10"}],
        "candidates": list(candidates),
    }
    capture = {
        "schema": "cinegraph.catalog-pilot-capture/v1",
        "selection_sha256": "c" * 64,
        "films": [{
            "qid": "Q10", "capture_status": "complete", "wikidata_status": "captured",
            "wikidata_revision": 87654, "wikidata_sha256": "e" * 64,
            "wikidata_capture_url": "https://www.wikidata.org/wiki/Special:EntityData/Q10.json",
            "wikidata_attribution_url": "https://www.wikidata.org/wiki/Q10",
            "wikidata_license": "CC0 1.0",
        }],
    }
    targets = {
        "schema": "cinegraph.credit-target-manifest/v1",
        "selection_sha256": "c" * 64,
        "targets": [{"qid": "Q20", "references": [{
            "film_qid": "Q10", "role": "cast", "source_revision": 87654,
            "source_sha256": "e" * 64, "statement_locator": "claims.P161[0]",
        }]}],
    }
    capture_bytes = json.dumps(capture, sort_keys=True).encode()
    target_bytes = json.dumps(targets, sort_keys=True).encode()
    person_bytes = ACTOR_SNAPSHOT_BYTES
    checkpoint = {
        "manifest_sha256": hashlib.sha256(target_bytes).hexdigest(),
        "captured": {"Q20": {
            "english_label": "Actor Name",
            "source_url": "https://www.wikidata.org/wiki/Special:EntityData/Q20.json",
            "source_revision": 98765,
            "sha256": hashlib.sha256(person_bytes).hexdigest(),
        }},
    }
    checkpoint_bytes = json.dumps(checkpoint, sort_keys=True).encode()
    report["film_capture_manifest_sha256"] = hashlib.sha256(capture_bytes).hexdigest()
    report["credit_target_manifest_sha256"] = hashlib.sha256(target_bytes).hexdigest()
    report["credit_label_checkpoint_sha256"] = hashlib.sha256(checkpoint_bytes).hexdigest()
    raw = json.dumps(report, sort_keys=True).encode()
    result = build_source_statement_manifest(
        report, raw, capture, capture_bytes, targets, target_bytes,
        checkpoint, checkpoint_bytes,
        {"Q20": person_bytes if actor_snapshot_override is None else actor_snapshot_override},
    )
    return result, raw


def test_same_film_cast_identity_yields_traceable_non_operational_statement_draft():
    result, raw = _build(_candidate())
    statement = result["source_statement_drafts"][0]

    assert result["input_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["operational_fact_write"] is False
    assert result["assertions_created"] is False
    assert result["schema"] == "cinegraph.wikipedia-cast-source-statements/v3"
    assert statement["source_property"] == "wikipedia_cast_credit_candidate"
    assert statement["raw_subject"] == {"film_qid": "Q10", "actor_qid": "Q20"}
    assert statement["raw_value"]["character_name_in_source"] == "Character"
    assert statement["raw_value"]["review_status"] == "review_required"
    assert statement["raw_qualifiers"]["passage_sha256"] == "a" * 64
    assert statement["raw_qualifiers"]["wikidata_actor_identity"] == {
        "entity_qid": "Q20", "entity_label": "Actor Name",
        "source_url": "https://www.wikidata.org/wiki/Special:EntityData/Q20.json",
        "source_revision": 98765,
        "snapshot_sha256": hashlib.sha256(ACTOR_SNAPSHOT_BYTES).hexdigest(),
        "license": "CC0 1.0",
    }
    assert statement["raw_qualifiers"]["wikidata_cast_statement_locators"] == ["claims.P161[0]"]
    assert statement["raw_qualifiers"]["matching_character_qids_by_label_only"] == ["Q30"]
    assert result["summary"]["character_qids_are_label_matches_only"] is True


def test_identity_only_suggestion_never_becomes_a_source_statement_draft():
    result, _ = _build(_candidate(
        actor_qid=None,
        actor_identity_qid="Q20",
        actor_identity_match="exact_unique_english_alias",
        identity_resolution="matched_captured_person_identity_only",
    ))

    assert result["source_statement_drafts"] == []
    assert result["summary"]["excluded"]["not_same_film_cast_identity"] == 1


@pytest.mark.parametrize("field,value", [
    ("wikipedia_url", "https://example.org/not-wikipedia"),
    ("wikipedia_license", "unknown"),
    ("review_status", "resolved"),
    ("wikipedia_snapshot_sha256", "broken"),
    ("passage_sha256", "broken"),
    ("character_name_in_source", "  "),
    ("actor_label", "Different Person"),
])
def test_incomplete_or_unbound_candidates_are_excluded(field, value):
    result, _ = _build(_candidate(**{field: value}))

    assert result["source_statement_drafts"] == []
    assert result["summary"]["excluded"]["invalid_or_incomplete"] == 1


def test_duplicate_candidate_statement_is_rejected():
    row = _candidate()
    with pytest.raises(ValueError, match="duplicate source statement"):
        _build(row, row)


def test_unknown_candidate_schema_is_rejected():
    report = {"schema": "cinegraph.wikipedia-cast-candidates/v6", "candidates": []}
    with pytest.raises(ValueError, match="v7"):
        build_source_statement_manifest(
            report, b"{}", {}, b"{}", {}, b"{}", {}, b"{}", {},
        )


def test_source_draft_validation_detects_mutated_content_and_character_label_metadata():
    result, _ = _build(_candidate())
    draft = result["source_statement_drafts"][0]
    draft["raw_qualifiers"]["matching_character_qids_by_label_only"] = ["Q999"]

    with pytest.raises(ValueError, match="content does not match"):
        validate_cast_source_statement_draft(draft)


@pytest.mark.parametrize("updates", [
    {"actor_identity_evidence": None},
    {"actor_identity_qid": "Q999"},
    {"actor_identity_label": ["not", "a", "label"]},
    {"actor_identity_label": {"malformed": "label"}},
    {"actor_statement_locators": ["claims.P999[0]"]},
    {"actor_identity_evidence": {"source_url": "https://www.wikidata.org/wiki/Q20", "source_revision": 12, "snapshot_sha256": "d" * 64}},
])
def test_identity_crosswalk_must_be_bound_to_exact_wikidata_person_evidence(updates):
    result, _ = _build(_candidate(**updates))
    assert result["source_statement_drafts"] == []
    assert sum(result["summary"]["excluded"].values()) == 1


def test_person_identity_snapshot_must_match_checkpoint_and_retained_bytes():
    result, _ = _build(_candidate(), actor_snapshot_override=b"{}")

    assert result["source_statement_drafts"] == []
    assert result["summary"]["excluded"]["invalid_or_incomplete"] == 1
