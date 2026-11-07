from __future__ import annotations

import hashlib
import json

import pytest

from app.services.wikidata_cast_character_crosswalk import (
    build_wikidata_cast_character_crosswalk,
    render_wikidata_cast_character_crosswalk,
    render_wikidata_cast_character_review_html,
)


def _entity_payload(entity: dict) -> bytes:
    return json.dumps({"entities": {entity["id"]: entity}}, sort_keys=True).encode()


def _partition():
    selection = "a" * 64
    film_entity = {
        "id": "Q10", "lastrevid": 123,
        "claims": {"P161": [{
            "rank": "normal",
            "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q20"}}},
            "qualifiers": {"P453": [{
                "snaktype": "value", "datavalue": {"value": {"id": "Q30"}},
            }]},
            "references": [{"hash": "fixture-reference"}],
        }]},
    }
    film_payload = _entity_payload(film_entity)
    film_sha = hashlib.sha256(film_payload).hexdigest()
    label_entity = {"id": "Q30", "lastrevid": 456, "labels": {"en": {"value": "Hero"}}}
    label_payload = _entity_payload(label_entity)
    label_sha = hashlib.sha256(label_payload).hexdigest()
    passage_content = "Fixture Actor as Hero: a sample role."
    passage = {
        "section_locator": "cast", "ordinal": 0, "content": passage_content,
        "content_sha256": hashlib.sha256(passage_content.encode()).hexdigest(),
    }
    passage_derivative = {
        "schema": "cinegraph.wikipedia-passage-extraction/v6",
        "parser_version": "enwiki-article-html-extraction-v6",
        "source_revision": 1001,
        "source_snapshot_sha256": "b" * 64,
        "passages": [passage],
    }
    passage_payload = json.dumps(passage_derivative, sort_keys=True).encode()
    passage_derivative_sha = hashlib.sha256(passage_payload).hexdigest()
    candidate = {
        "schema": "cinegraph.wikipedia-cast-candidates/v8",
        "selection_sha256": selection,
        "films": [{
            "selection_rank": 1, "film_qid": "Q10", "title": "Fixture Film", "year": 2020,
            "source_revision": 1001, "source_sha256": "b" * 64,
        }],
        "candidates": [{
            "film_qid": "Q10", "actor_qid": "Q20", "actor_label": "Fixture Actor",
            "identity_resolution": "same_film_wikidata_cast_target",
            "actor_statement_locators": ["claims.P161[0]"],
            "character_name_in_source": "Hero", "review_status": "review_required",
            "wikipedia_revision": 1001, "wikipedia_snapshot_sha256": "b" * 64,
            "wikipedia_url": "https://en.wikipedia.org/wiki/Fixture_Film",
            "section_locator": "cast", "passage_sha256": passage["content_sha256"],
            "passage_ordinal": 0, "evidence_phrase": passage_content,
        }],
    }
    capture = {
        "schema": "cinegraph.catalog-pilot-capture/v1", "selection_sha256": selection,
        "films": [{
            "qid": "Q10", "title": "Fixture Film", "year": 2020,
            "selection_rank": 1, "identity_status": "verified", "capture_status": "complete",
            "wikipedia_status": "captured", "wikipedia_revision": 1001,
            "wikipedia_sha256": "b" * 64, "wikidata_status": "captured",
            "wikidata_revision": 123, "wikidata_sha256": film_sha,
            "passage_derivative_sha256": passage_derivative_sha,
            "wikipedia_attribution_url": "https://en.wikipedia.org/wiki/Fixture_Film",
        }],
    }
    targets = {
        "schema": "cinegraph.credit-target-manifest/v1", "selection_sha256": selection,
        "targets": [{"qid": "Q30", "references": [{
            "film_qid": "Q10", "role": "character", "person_qid": "Q20",
            "statement_locator": "claims.P161[0]", "qualifier_locator": "qualifiers.P453[0]",
            "source_revision": 123, "source_sha256": film_sha,
        }]}],
    }
    target_bytes = json.dumps(targets, sort_keys=True).encode()
    label_checkpoint = {
        "manifest_sha256": hashlib.sha256(target_bytes).hexdigest(),
        "captured": {"Q30": {"english_label": "Hero", "sha256": label_sha, "source_revision": 456}},
    }
    candidate["film_capture_manifest_sha256"] = hashlib.sha256(json.dumps(capture, sort_keys=True).encode()).hexdigest()
    candidate["credit_target_manifest_sha256"] = hashlib.sha256(target_bytes).hexdigest()
    label_checkpoint_bytes = json.dumps(label_checkpoint, sort_keys=True).encode()
    candidate["credit_label_checkpoint_sha256"] = hashlib.sha256(label_checkpoint_bytes).hexdigest()
    candidate_bytes = json.dumps(candidate, sort_keys=True).encode()
    capture_bytes = json.dumps(capture, sort_keys=True).encode()
    part = {
        "candidate_report": candidate,
        "capture_manifest": capture,
        "credit_target_manifest": targets,
        "label_checkpoint": label_checkpoint,
        "raw_bytes": {
            "candidate_report": candidate_bytes,
            "capture_manifest": capture_bytes,
            "credit_target_manifest": target_bytes,
            "label_checkpoint": label_checkpoint_bytes,
        },
        "film_snapshots": {"Q10": (json.loads(film_payload), film_payload)},
        "passage_snapshots": {"Q10": (passage_derivative, passage_payload)},
        "passage_derivative_bindings": {"Q10": {
            "passage_derivative_sha256": passage_derivative_sha,
            "parser_version": "enwiki-article-html-extraction-v6",
        }},
        "label_snapshot_payloads": {"Q30": label_payload},
    }
    return part


def test_crosswalk_verifies_direct_claim_and_separate_source_text_label_agreement():
    report = build_wikidata_cast_character_crosswalk([_partition()])

    assert report["summary"]["direct_p453_links"] == 1
    assert report["summary"]["exact_character_label_agreements"] == 1
    link = report["direct_links"][0]
    assert link["actor_qid"] == "Q20"
    assert link["character_qid"] == "Q30"
    assert link["wikidata_statement_reference_count"] == 1
    assert link["review_status"] == "review_required"
    assert report["summary"]["operational_assertions_written"] is False
    assert "?oldid=123" in render_wikidata_cast_character_crosswalk(report)
    html_report = render_wikidata_cast_character_review_html(report)
    assert 'id="agreement"' in html_report
    assert "Wikipedia r1001" in html_report
    assert "Review status remains required" in html_report


def test_crosswalk_rejects_credit_target_that_disagrees_with_retained_p161_p453():
    part = _partition()
    part["credit_target_manifest"]["targets"][0]["references"][0]["character_qid"] = "Q31"
    # Character QIDs are represented by each target row's qid; bind a conflicting target row.
    part["credit_target_manifest"]["targets"][0]["qid"] = "Q31"
    target_bytes = json.dumps(part["credit_target_manifest"], sort_keys=True).encode()
    part["raw_bytes"]["credit_target_manifest"] = target_bytes
    part["candidate_report"]["credit_target_manifest_sha256"] = hashlib.sha256(target_bytes).hexdigest()
    part["raw_bytes"]["candidate_report"] = json.dumps(part["candidate_report"], sort_keys=True).encode()
    part["label_checkpoint"]["manifest_sha256"] = hashlib.sha256(target_bytes).hexdigest()
    checkpoint_bytes = json.dumps(part["label_checkpoint"], sort_keys=True).encode()
    part["raw_bytes"]["label_checkpoint"] = checkpoint_bytes
    part["candidate_report"]["credit_label_checkpoint_sha256"] = hashlib.sha256(checkpoint_bytes).hexdigest()
    part["raw_bytes"]["candidate_report"] = json.dumps(part["candidate_report"], sort_keys=True).encode()

    with pytest.raises(ValueError, match="values disagree"):
        build_wikidata_cast_character_crosswalk([part])


def test_crosswalk_rejects_candidate_evidence_not_present_in_retained_passage():
    part = _partition()
    part["candidate_report"]["candidates"][0]["evidence_phrase"] = "Invented Actor as Hero"

    with pytest.raises(ValueError, match="not present in its retained passage"):
        build_wikidata_cast_character_crosswalk([part])


def test_review_html_escapes_source_derived_text():
    report = build_wikidata_cast_character_crosswalk([_partition()])
    report["direct_links"][0]["film_title"] = '<script>alert("x")</script>'

    rendered = render_wikidata_cast_character_review_html(report)

    assert '<script>alert("x")</script>' not in rendered
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in rendered
