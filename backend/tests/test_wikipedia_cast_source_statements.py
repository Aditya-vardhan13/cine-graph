import hashlib
import json

import pytest

from app.services.wikipedia_cast_source_statements import build_source_statement_manifest


def _candidate(**updates):
    row = {
        "film_qid": "Q10",
        "actor_qid": "Q20",
        "actor_identity_qid": "Q20",
        "identity_resolution": "same_film_wikidata_cast_target",
        "actor_identity_match": "same_film_wikidata_cast_target",
        "actor_label": "Actor Name",
        "actor_label_in_source": "Actor Name",
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


def _build(*candidates):
    report = {
        "schema": "cinegraph.wikipedia-cast-candidates/v7",
        "selection_sha256": "c" * 64,
        "candidates": list(candidates),
    }
    raw = json.dumps(report, sort_keys=True).encode()
    return build_source_statement_manifest(report, raw), raw


def test_same_film_cast_identity_yields_traceable_non_operational_statement_draft():
    result, raw = _build(_candidate())
    statement = result["source_statement_drafts"][0]

    assert result["input_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["operational_fact_write"] is False
    assert result["assertions_created"] is False
    assert statement["source_property"] == "wikipedia_cast_credit_candidate"
    assert statement["raw_subject"] == {"film_qid": "Q10", "actor_qid": "Q20"}
    assert statement["raw_value"]["character_name_in_source"] == "Character"
    assert statement["raw_value"]["review_status"] == "review_required"
    assert statement["raw_qualifiers"]["passage_sha256"] == "a" * 64
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
        build_source_statement_manifest(report, b"{}")
