from __future__ import annotations

import hashlib
import json
from copy import deepcopy

import pytest

from app.services.wikipedia_cast_candidate_coverage import (
    build_cast_candidate_coverage,
    render_cast_candidate_coverage,
)
from app.services.wikipedia_cast_source_statements import (
    EXTRACTOR_VERSION,
    SOURCE_PROPERTY,
    statement_digest_for_fields,
)


def _partition(film_ranks: range, *, selection_sha256: str = "s" * 64,
              identity_only: bool = False):
    capture_manifest_sha = hashlib.sha256(f"capture-{selection_sha256}".encode()).hexdigest()
    credit_target_manifest_sha = hashlib.sha256(f"targets-{selection_sha256}".encode()).hexdigest()
    films = []
    candidates = []
    drafts = []
    for rank in film_ranks:
        qid = f"Q{rank + 1000}"
        url = f"https://en.wikipedia.org/wiki/Film_{rank}"
        snapshot_hash = hashlib.sha256(f"snapshot-{rank}".encode()).hexdigest()
        film = {
            "selection_rank": rank,
            "film_qid": qid,
            "title": f"Film {rank}",
            "year": 2000 + rank,
            "source_revision": 9000 + rank,
            "source_sha256": snapshot_hash,
            "cast_passages": 1,
            "candidate_count": 1,
            "ambiguous_or_unmatched_count": 0,
        }
        films.append(film)
        actor_source_name = f"Alias {rank}" if identity_only else f"Actor {rank}"
        identity_match = "exact_unique_english_alias" if identity_only else "same_film_wikidata_cast_target"
        candidate = {
            "selection_rank": rank,
            "film_qid": qid,
            "film_title": film["title"],
            "film_year": film["year"],
            "wikipedia_revision": film["source_revision"],
            "wikipedia_snapshot_sha256": snapshot_hash,
            "wikipedia_url": url,
            "wikipedia_license": "CC BY-SA 4.0",
            "actor_qid": None if identity_only else f"Q{rank + 2000}",
            "actor_identity_qid": f"Q{rank + 2000}",
            "actor_identity_label": f"Actor {rank}",
            "actor_identity_evidence": {
                "source_url": f"https://www.wikidata.org/wiki/Special:EntityData/Q{rank + 2000}.json",
                "source_revision": 10000 + rank,
                "snapshot_sha256": "d" * 64,
            },
            "actor_statement_locators": [] if identity_only else [f"claims.P161[{rank}]"],
            "actor_label_in_source": actor_source_name,
            "character_name_in_source": f"Character {rank}",
            "evidence_phrase": f"{actor_source_name} as Character {rank}",
            "section_locator": "cast",
            "passage_ordinal": 0,
            "passage_sha256": hashlib.sha256(f"passage-{rank}".encode()).hexdigest(),
            "identity_resolution": "matched_captured_person_identity_only" if identity_only else "same_film_wikidata_cast_target",
            "actor_identity_match": identity_match,
            "matching_wikidata_character_qids": [],
            "review_status": "review_required",
        }
        candidates.append(candidate)
        subject = {"film_qid": qid, "actor_qid": f"Q{rank + 2000}"}
        value = {
            "actor_label_in_source": actor_source_name,
            "character_name_in_source": f"Character {rank}",
            "review_status": "review_required",
        }
        qualifiers = {
            "wikipedia_url": url,
            "wikipedia_revision": film["source_revision"],
            "wikipedia_snapshot_sha256": snapshot_hash,
            "wikipedia_license": "CC BY-SA 4.0",
            "attribution_url": url,
            "section_locator": "cast",
            "passage_ordinal": 0,
            "passage_sha256": hashlib.sha256(f"passage-{rank}".encode()).hexdigest(),
            "evidence_phrase": f"{actor_source_name} as Character {rank}",
            "wikidata_actor_identity": {
                "entity_qid": subject["actor_qid"], "entity_label": f"Actor {rank}",
                "source_url": f"https://www.wikidata.org/wiki/Special:EntityData/{subject['actor_qid']}.json",
                "source_revision": 10000 + rank, "snapshot_sha256": "d" * 64,
                "license": "CC0 1.0",
            },
            "wikidata_cast_statement_locators": [] if identity_only else [f"claims.P161[{rank}]"],
            "identity_resolution_basis": identity_match,
            "wikidata_film_identity_source": {
                "film_qid": qid,
                "source_url": f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
                "attribution_url": f"https://www.wikidata.org/wiki/{qid}",
                "source_revision": 11000 + rank,
                "snapshot_sha256": "e" * 64,
                "license": "CC0 1.0",
            },
            "wikidata_film_cast_evidence": None if identity_only else {
                "film_qid": qid,
                "source_url": f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
                "attribution_url": f"https://www.wikidata.org/wiki/{qid}",
                "source_revision": 11000 + rank,
                "snapshot_sha256": "e" * 64,
                "license": "CC0 1.0",
                "statement_references": [{
                    "statement_locator": f"claims.P161[{rank}]",
                    "source_revision": 11000 + rank,
                    "snapshot_sha256": "e" * 64,
                }],
            },
            "matching_character_qids_by_label_only": [],
        }
        digest = statement_digest_for_fields(
            source_property=SOURCE_PROPERTY,
            extractor_version=EXTRACTOR_VERSION,
            raw_subject=subject,
            raw_value=value,
            raw_qualifiers=qualifiers,
        )
        drafts.append({
            "source_property": SOURCE_PROPERTY,
            "extractor_version": EXTRACTOR_VERSION,
            "statement_locator": f"cast-candidate/{digest}",
            "raw_subject": subject,
            "raw_value": {**value, "statement_digest": digest},
            "raw_qualifiers": qualifiers,
        })

    report = {
        "schema": "cinegraph.wikipedia-cast-candidates/v8",
        "selection_sha256": selection_sha256,
        "film_capture_manifest_sha256": capture_manifest_sha,
        "credit_target_manifest_sha256": credit_target_manifest_sha,
        "credit_label_checkpoint_sha256": "c" * 64,
        "operational_fact_write": False,
        "films": films,
        "candidates": candidates,
        "ambiguities": [],
        "summary": {
            "films": len(films),
            "candidate_rows": len(candidates),
            "ambiguous_or_unmatched_rows": 0,
            "films_with_cast_passages": len(films),
            "wikidata_actor_candidates": 0 if identity_only else len(candidates),
            "source_only_identity_matches": len(candidates) if identity_only else 0,
            "source_only_unresolved_candidates": 0,
            "candidates_matching_wikidata_character_label": 0,
            "films_with_candidates": len(films),
        },
    }
    report_bytes = json.dumps(report, sort_keys=True).encode()
    manifest = {
        "schema": "cinegraph.wikipedia-cast-source-statements/v5",
        "input_schema": report["schema"],
        "input_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "capture_manifest_sha256": capture_manifest_sha,
        "credit_target_manifest_sha256": credit_target_manifest_sha,
        "credit_label_checkpoint_sha256": "c" * 64,
        "selection_sha256": selection_sha256,
        "operational_fact_write": False,
        "assertions_created": False,
        "summary": {"source_statement_drafts": len(drafts)},
        "source_statement_drafts": drafts,
    }
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    return (report, report_bytes), (manifest, manifest_bytes)


def _pilot(candidate_inputs):
    films = [
        {
            "selection_rank": film["selection_rank"],
            "wikidata_id": film["film_qid"],
            "input_title": film["title"],
            "input_year": film["year"],
        }
        for report, _ in candidate_inputs
        for film in report["films"]
    ]
    manifest = {"film_count": len(films), "films": films}
    return manifest, json.dumps(manifest, sort_keys=True).encode()


def _unresolved_identity_supplement():
    candidate, statements = _partition(range(1, 2))
    report, _ = candidate
    manifest, _ = statements
    candidate_row = report["candidates"][0]
    candidate_row.update({
        "actor_qid": None,
        "actor_identity_qid": None,
        "actor_identity_label": None,
        "actor_identity_evidence": None,
        "actor_statement_locators": [],
        "actor_identity_match": "no_exact_captured_person_label_or_alias",
        "identity_resolution": "unresolved_source_name",
    })
    report["summary"].update({
        "wikidata_actor_candidates": 0,
        "source_only_identity_matches": 0,
        "source_only_unresolved_candidates": 1,
    })
    draft = deepcopy(manifest["source_statement_drafts"][0])
    qid = "Q2001"
    qualifiers = draft["raw_qualifiers"]
    qualifiers["identity_resolution_basis"] = "exact_unique_english_label"
    qualifiers["wikidata_actor_identity"] = {
        "entity_qid": qid,
        "entity_label": "Actor 1",
        "source_url": f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
        "source_revision": 12001,
        "snapshot_sha256": "f" * 64,
        "license": "CC0 1.0",
    }
    qualifiers["wikidata_cast_statement_locators"] = []
    qualifiers["wikidata_film_cast_evidence"] = None
    draft["raw_subject"]["actor_qid"] = qid
    digest = statement_digest_for_fields(
        source_property=draft["source_property"],
        extractor_version=draft["extractor_version"],
        raw_subject=draft["raw_subject"],
        raw_value=draft["raw_value"],
        raw_qualifiers=qualifiers,
    )
    draft["raw_value"]["statement_digest"] = digest
    draft["statement_locator"] = f"cast-candidate/{digest}"
    manifest["source_statement_drafts"] = [draft]
    manifest["summary"]["identity_only_drafts"] = 1
    manifest["identity_supplement"] = {
        "schema": "cinegraph.wikipedia-cast-identity-supplement/v1",
        "sha256": hashlib.sha256(b"retained identity supplement manifest").hexdigest(),
    }
    report_bytes = json.dumps(report, sort_keys=True).encode()
    manifest["input_sha256"] = hashlib.sha256(report_bytes).hexdigest()
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
    return (report, report_bytes), (manifest, manifest_bytes)


def test_curated_identity_supplement_resolves_only_the_exact_unresolved_source_passage():
    candidate, statements = _unresolved_identity_supplement()
    report = build_cast_candidate_coverage(
        [candidate], [statements], _pilot([candidate]), expected_film_count=1,
    )

    assert report["schema"] == "cinegraph.wikipedia-cast-candidate-coverage/v2"
    assert report["summary"]["same_film_identity_candidates"] == 0
    assert report["summary"]["identity_only_suggestions"] == 1
    assert report["summary"]["identity_supplemented_candidates"] == 1
    assert report["summary"]["unresolved_source_names"] == 0
    assert report["summary"]["review_only_source_statement_drafts"] == 1
    assert report["films"][0]["source_statement_drafts"] == 1
    assert "remain unverified" in render_cast_candidate_coverage(report)


def test_identity_supplement_cannot_attach_a_valid_draft_to_a_different_phrase():
    candidate, statements = _unresolved_identity_supplement()
    report, report_bytes = candidate
    manifest, _ = statements
    draft = manifest["source_statement_drafts"][0]
    draft["raw_qualifiers"]["evidence_phrase"] = "Forged Actor 1 as Character 1"
    digest = statement_digest_for_fields(
        source_property=draft["source_property"],
        extractor_version=draft["extractor_version"],
        raw_subject=draft["raw_subject"],
        raw_value=draft["raw_value"],
        raw_qualifiers=draft["raw_qualifiers"],
    )
    draft["raw_value"]["statement_digest"] = digest
    draft["statement_locator"] = f"cast-candidate/{digest}"
    manifest["input_sha256"] = hashlib.sha256(report_bytes).hexdigest()
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()

    with pytest.raises(ValueError, match="unique unresolved candidate passage"):
        build_cast_candidate_coverage(
            [(report, report_bytes)], [(manifest, manifest_bytes)],
            _pilot([(report, report_bytes)]), expected_film_count=1,
        )


def test_combines_complete_disjoint_partitions_and_renders_passage_free_review_sheet():
    first_report, first_statements = _partition(range(1, 2))
    second_report, second_statements = _partition(range(2, 3), selection_sha256="t" * 64)
    candidates = [first_report, second_report]

    result = build_cast_candidate_coverage(
        candidates, [first_statements, second_statements], _pilot(candidates),
        expected_film_count=2,
    )
    markdown = render_cast_candidate_coverage(result)

    assert result["summary"]["films"] == 2
    assert result["summary"]["candidate_rows"] == 2
    assert result["summary"]["review_only_source_statement_drafts"] == 2
    assert [row["selection_rank"] for row in result["films"]] == [1, 2]
    assert "Captured article" in markdown
    assert "passage text is reproduced" in markdown
    assert "Film 1 (2001)" in markdown
    assert "?oldid=9001" in markdown


def test_identity_only_candidate_is_bound_as_a_review_draft_without_cast_membership_claim():
    candidate, statements = _partition(range(1, 2), identity_only=True)
    report = build_cast_candidate_coverage(
        [candidate], [statements], _pilot([candidate]), expected_film_count=1,
    )

    assert report["summary"]["same_film_identity_candidates"] == 0
    assert report["summary"]["identity_only_suggestions"] == 1
    assert report["summary"]["identity_only_candidates_with_review_drafts"] == 1
    assert report["summary"]["review_only_source_statement_drafts"] == 1


def test_accepts_the_frozen_catalog_pilot_nested_identity_when_unique():
    candidate, statements = _partition(range(1, 2))
    pilot = {
        "film_count": 1,
        "films": [{
            "selection_rank": 1,
            "input_title": "Film 1",
            "input_year": 2001,
            "catalog_candidates": [{"wikidata_id": "Q1001"}],
        }],
    }
    pilot_bytes = json.dumps(pilot, sort_keys=True).encode()

    report = build_cast_candidate_coverage(
        [candidate], [statements], (pilot, pilot_bytes), expected_film_count=1,
    )

    assert report["summary"]["films"] == 1


def test_rejects_ambiguous_nested_catalog_pilot_identity():
    candidate, statements = _partition(range(1, 2))
    pilot = {
        "film_count": 1,
        "films": [{
            "selection_rank": 1,
            "catalog_candidates": [{"wikidata_id": "Q1001"}, {"wikidata_id": "Q2001"}],
        }],
    }
    pilot_bytes = json.dumps(pilot, sort_keys=True).encode()

    with pytest.raises(ValueError, match="exactly one catalog identity"):
        build_cast_candidate_coverage(
            [candidate], [statements], (pilot, pilot_bytes), expected_film_count=1,
        )


def test_rejects_report_manifest_pair_when_statement_bundle_is_not_exact_input():
    candidate, statements = _partition(range(1, 2))
    candidates = [candidate]
    changed_report, _ = _partition(range(1, 2))
    changed_report[0]["summary"]["candidate_rows"] = 2
    changed_bytes = json.dumps(changed_report[0], sort_keys=True).encode()

    with pytest.raises(ValueError, match="exact candidate-report bytes"):
        build_cast_candidate_coverage(
            [(changed_report[0], changed_bytes)], [statements],
            _pilot([(changed_report[0], changed_bytes)]), expected_film_count=1,
        )


def test_rejects_tampered_statement_content_even_when_source_binding_matches():
    candidate, statements = _partition(range(1, 2))
    manifest, _ = statements
    manifest["source_statement_drafts"][0]["raw_value"]["character_name_in_source"] = "Wrong Character"
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()

    with pytest.raises(ValueError, match="content does not match"):
        build_cast_candidate_coverage(
            [candidate], [(manifest, manifest_bytes)], _pilot([candidate]), expected_film_count=1,
        )


def test_rejects_valid_draft_that_does_not_match_its_candidate_evidence_row():
    candidate, statements = _partition(range(1, 2))
    report, _ = candidate
    report["candidates"][0]["character_name_in_source"] = "A different, still syntactically valid role"
    candidate_bytes = json.dumps(report, sort_keys=True).encode()
    manifest, _ = statements
    manifest["input_sha256"] = hashlib.sha256(candidate_bytes).hexdigest()
    manifest_bytes = json.dumps(manifest, sort_keys=True).encode()

    with pytest.raises(ValueError, match="do not match their exact candidate evidence rows"):
        build_cast_candidate_coverage(
            [(report, candidate_bytes)], [(manifest, manifest_bytes)],
            _pilot([(report, candidate_bytes)]), expected_film_count=1,
        )
