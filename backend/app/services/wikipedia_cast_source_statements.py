"""Turn retained cast candidates into immutable-source statement drafts.

This adapter produces a local replay manifest only.  It does not create
SourceAssertion or Assertion rows, and matching a Wikipedia name to a
Wikidata cast label does not approve the actor-character credit.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from urllib.parse import urlparse


SCHEMA = "cinegraph.wikipedia-cast-source-statements/v5"
INPUT_SCHEMA = "cinegraph.wikipedia-cast-candidates/v8"
EXTRACTOR_VERSION = "wikipedia-cast-candidate-source-statement-v5"
LEGACY_SCHEMA = "cinegraph.wikipedia-cast-source-statements/v4"
LEGACY_EXTRACTOR_VERSION = "wikipedia-cast-candidate-source-statement-v4"
SOURCE_PROPERTY = "wikipedia_cast_credit_candidate"
_QID = re.compile(r"^Q[1-9][0-9]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_P161_LOCATOR = re.compile(r"^claims\.P161\[\d+\]$")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def english_person_name_match_basis(
    source_name: str, english_label: str, english_aliases: set[str],
) -> str | None:
    """Return the exact retained English-name basis, preferring the label."""
    normalized_source = _normalized(source_name)
    if normalized_source == _normalized(english_label):
        return "exact_unique_english_label"
    if any(normalized_source == _normalized(alias) for alias in english_aliases):
        return "exact_unique_english_alias"
    return None


def statement_digest_for_fields(
    *, source_property: str, extractor_version: str,
    raw_subject: dict[str, Any], raw_value: dict[str, Any], raw_qualifiers: dict[str, Any],
) -> str:
    """Hash a complete draft body; the locator/digest are checked separately."""
    value = {key: item for key, item in raw_value.items() if key != "statement_digest"}
    identity = {
        "source_property": source_property,
        "extractor_version": extractor_version,
        "raw_subject": raw_subject,
        "raw_value": value,
        "raw_qualifiers": raw_qualifiers,
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_source_statement_manifest(
    candidate_report: dict[str, Any], report_bytes: bytes,
    capture_manifest: dict[str, Any], capture_bytes: bytes,
    credit_target_manifest: dict[str, Any], credit_target_bytes: bytes,
    credit_label_checkpoint: dict[str, Any], checkpoint_bytes: bytes,
    actor_snapshot_bytes: dict[str, bytes],
) -> dict[str, Any]:
    """Create review-only drafts for strong identities, with evidence basis explicit.

    A same-film P161 actor match and a unique captured English person
    label/alias match are separate evidence bases. Identity-only rows have no
    film-side P161 claim; they remain review-required and require a human to
    verify the article's credit before any operational projection.
    """
    if candidate_report.get("schema") != INPUT_SCHEMA:
        raise ValueError("Expected the v7 retained Wikipedia cast candidate report")
    if capture_manifest.get("schema") != "cinegraph.catalog-pilot-capture/v1":
        raise ValueError("Expected the exact retained film capture manifest")
    if credit_target_manifest.get("schema") != "cinegraph.credit-target-manifest/v1":
        raise ValueError("Expected the exact audited Wikidata credit-target manifest")
    capture_hash = hashlib.sha256(capture_bytes).hexdigest()
    credit_hash = hashlib.sha256(credit_target_bytes).hexdigest()
    checkpoint_hash = hashlib.sha256(checkpoint_bytes).hexdigest()
    selection = candidate_report.get("selection_sha256")
    if (candidate_report.get("film_capture_manifest_sha256") != capture_hash
            or candidate_report.get("credit_target_manifest_sha256") != credit_hash
            or candidate_report.get("credit_label_checkpoint_sha256") != checkpoint_hash
            or capture_manifest.get("selection_sha256") != selection
            or credit_target_manifest.get("selection_sha256") != selection
            or credit_label_checkpoint.get("manifest_sha256") != credit_hash):
        raise ValueError("Candidate, capture, credit-target and person-label manifests are not the exact bound inputs")

    capture_films = capture_manifest.get("films")
    target_rows = credit_target_manifest.get("targets")
    captured_people = credit_label_checkpoint.get("captured")
    if (not isinstance(capture_films, list) or not isinstance(target_rows, list)
            or not isinstance(captured_people, dict)):
        raise ValueError("Capture, credit-target and person-label manifests have malformed rows")
    films_by_qid = {
        row.get("qid"): row for row in capture_films
        if isinstance(row, dict) and isinstance(row.get("qid"), str)
    }
    if len(films_by_qid) != len(capture_films):
        raise ValueError("Capture manifest contains duplicate or malformed film QIDs")
    targets_by_qid = {
        row.get("qid"): row for row in target_rows
        if isinstance(row, dict) and isinstance(row.get("qid"), str)
    }
    if len(targets_by_qid) != len(target_rows):
        raise ValueError("Credit-target manifest contains duplicate or malformed entity QIDs")
    candidates = candidate_report.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("Candidate report must contain a candidates array")

    statements: list[dict[str, Any]] = []
    excluded = {"unresolved_or_ambiguous_identity": 0, "invalid_or_incomplete": 0}
    identity_only_drafts = 0
    seen_locators: set[tuple[str, str]] = set()
    for row in candidates:
        if not isinstance(row, dict):
            raise ValueError("Candidate rows must be objects")
        resolution = row.get("identity_resolution")
        same_film_match = (
            resolution == "same_film_wikidata_cast_target"
            and row.get("actor_identity_match") == "same_film_wikidata_cast_target"
            and isinstance(row.get("actor_qid"), str)
            and row.get("actor_identity_qid") == row.get("actor_qid")
        )
        identity_only_match = (
            resolution == "matched_captured_person_identity_only"
            and row.get("actor_identity_match") in {
                "exact_unique_english_label", "exact_unique_english_alias",
            }
            and row.get("actor_qid") is None
            and isinstance(row.get("actor_identity_qid"), str)
            and row.get("actor_statement_locators") == []
        )
        actor_qid = row.get("actor_qid") if same_film_match else row.get("actor_identity_qid")
        if (not (same_film_match or identity_only_match)
                or not isinstance(actor_qid, str) or not _QID.fullmatch(actor_qid)):
            excluded["unresolved_or_ambiguous_identity"] += 1
            continue

        film_qid = row.get("film_qid")
        source_url = row.get("wikipedia_url")
        revision = row.get("wikipedia_revision")
        snapshot_hash = row.get("wikipedia_snapshot_sha256")
        passage_hash = row.get("passage_sha256")
        actor_label = row.get("actor_label_in_source")
        character = row.get("character_name_in_source")
        phrase = row.get("evidence_phrase")
        locator = row.get("section_locator")
        ordinal = row.get("passage_ordinal")
        if (not isinstance(film_qid, str) or not _QID.fullmatch(film_qid)
                or not isinstance(source_url, str)
                or urlparse(source_url).scheme != "https"
                or urlparse(source_url).hostname != "en.wikipedia.org"
                or not urlparse(source_url).path.startswith("/wiki/")
                or not isinstance(revision, int) or isinstance(revision, bool) or revision < 1
                or not isinstance(snapshot_hash, str) or not _SHA256.fullmatch(snapshot_hash)
                or not isinstance(passage_hash, str) or not _SHA256.fullmatch(passage_hash)
                or not isinstance(locator, str) or not locator
                or not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0
                or not isinstance(row.get("wikipedia_license"), str)
                or row["wikipedia_license"] != "CC BY-SA 4.0"
                or row.get("review_status") != "review_required"):
            excluded["invalid_or_incomplete"] += 1
            continue
        try:
            actor_label = _text(actor_label, "actor_label_in_source")
            character = _text(character, "character_name_in_source")
            phrase = _text(phrase, "evidence_phrase")
        except ValueError:
            excluded["invalid_or_incomplete"] += 1
            continue
        if (same_film_match
                and _normalized(actor_label) != _normalized(str(row.get("actor_label") or ""))):
            excluded["invalid_or_incomplete"] += 1
            continue
        identity_evidence = row.get("actor_identity_evidence")
        identity_url = identity_evidence.get("source_url") if isinstance(identity_evidence, dict) else None
        identity_revision = identity_evidence.get("source_revision") if isinstance(identity_evidence, dict) else None
        identity_hash = identity_evidence.get("snapshot_sha256") if isinstance(identity_evidence, dict) else None
        identity_locators = row.get("actor_statement_locators")
        film_qid = row.get("film_qid")
        parsed_identity_url = urlparse(identity_url) if isinstance(identity_url, str) else None
        captured_person = captured_people.get(actor_qid)
        person_payload = actor_snapshot_bytes.get(actor_qid)
        try:
            person_entity = json.loads(person_payload).get("entities", {}).get(actor_qid, {}) if isinstance(person_payload, bytes) else {}
        except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
            person_entity = {}
        person_labels = person_entity.get("labels") if isinstance(person_entity, dict) else None
        person_label_row = person_labels.get("en") if isinstance(person_labels, dict) else None
        person_label = person_label_row.get("value") if isinstance(person_label_row, dict) else None
        aliases_by_language = person_entity.get("aliases") if isinstance(person_entity, dict) else None
        person_aliases = aliases_by_language.get("en", []) if isinstance(aliases_by_language, dict) else []
        alias_labels = {
            alias.get("value") for alias in person_aliases
            if isinstance(alias, dict) and isinstance(alias.get("value"), str)
        }
        candidate_identity_label = row.get("actor_identity_label")
        identity_label_matches = (
            isinstance(person_entity, dict)
            and isinstance(candidate_identity_label, str)
            and (person_label == candidate_identity_label
                 or candidate_identity_label in alias_labels)
        )
        source_name_basis = (
            english_person_name_match_basis(actor_label, person_label, alias_labels)
            if isinstance(actor_label, str) and isinstance(person_label, str) else None
        )
        valid_identity_locators = (
            isinstance(identity_locators, list)
            and len(set(identity_locators)) == len(identity_locators)
            and all(isinstance(value, str) and _P161_LOCATOR.fullmatch(value)
                    for value in identity_locators)
        )
        if (row.get("actor_identity_qid") != actor_qid
                or (same_film_match and row.get("actor_identity_match") != "same_film_wikidata_cast_target")
                or (identity_only_match and source_name_basis != row.get("actor_identity_match"))
                or not isinstance(row.get("actor_identity_label"), str)
                or not row["actor_identity_label"].strip()
                or parsed_identity_url is None
                or parsed_identity_url.scheme != "https"
                or parsed_identity_url.hostname != "www.wikidata.org"
                or parsed_identity_url.path != f"/wiki/Special:EntityData/{actor_qid}.json"
                or parsed_identity_url.query or parsed_identity_url.fragment
                or not isinstance(identity_revision, int) or isinstance(identity_revision, bool)
                or identity_revision < 1
                or not isinstance(identity_hash, str) or not _SHA256.fullmatch(identity_hash)
                or not isinstance(captured_person, dict)
                or captured_person.get("source_url") != identity_url
                or captured_person.get("source_revision") != identity_revision
                or captured_person.get("sha256") != identity_hash
                or not isinstance(person_payload, bytes)
                or hashlib.sha256(person_payload).hexdigest() != identity_hash
                or person_entity.get("id") != actor_qid
                or person_entity.get("lastrevid") != identity_revision
                or not identity_label_matches
                or not valid_identity_locators
                or (same_film_match and not identity_locators)
                or (identity_only_match and identity_locators)):
            excluded["invalid_or_incomplete"] += 1
            continue
        film_capture = films_by_qid.get(film_qid)
        cast_target = targets_by_qid.get(actor_qid)
        if (film_capture is None or (same_film_match and cast_target is None)
                or film_capture.get("capture_status") != "complete"
                or film_capture.get("wikidata_status") != "captured"
                or film_capture.get("wikidata_license") != "CC0 1.0"
                or not isinstance(film_capture.get("wikidata_revision"), int)
                or not isinstance(film_capture.get("wikidata_sha256"), str)
                or not _SHA256.fullmatch(film_capture["wikidata_sha256"])):
            excluded["invalid_or_incomplete"] += 1
            continue
        matching_references: list[dict[str, Any]] = []
        if same_film_match:
            references = cast_target.get("references") if isinstance(cast_target, dict) else None
            if not isinstance(references, list):
                excluded["invalid_or_incomplete"] += 1
                continue
            matching_references = [reference for reference in references
                                   if isinstance(reference, dict)
                                   and reference.get("film_qid") == film_qid
                                   and reference.get("role") == "cast"
                                   and reference.get("statement_locator") in identity_locators]
            if (not matching_references
                    or {reference["statement_locator"] for reference in matching_references} != set(identity_locators)
                    or any(
                reference.get("source_revision") != film_capture.get("wikidata_revision")
                or reference.get("source_sha256") != film_capture.get("wikidata_sha256")
                for reference in matching_references
            )):
                excluded["invalid_or_incomplete"] += 1
                continue
        elif row.get("actor_identity_match") not in {
            "exact_unique_english_label", "exact_unique_english_alias",
        }:
            excluded["invalid_or_incomplete"] += 1
            continue

        raw_subject = {"film_qid": film_qid, "actor_qid": actor_qid}
        raw_value = {
            "actor_label_in_source": actor_label,
            "character_name_in_source": character,
            "review_status": "review_required",
        }
        raw_qualifiers = {
            "wikipedia_url": source_url,
            "wikipedia_revision": revision,
            "wikipedia_snapshot_sha256": snapshot_hash,
            "wikipedia_license": "CC BY-SA 4.0",
            "attribution_url": source_url,
            "section_locator": locator,
            "passage_ordinal": ordinal,
            "passage_sha256": passage_hash,
            "evidence_phrase": phrase,
            "wikidata_actor_identity": {
                "entity_qid": actor_qid,
                "entity_label": row["actor_identity_label"].strip(),
                "source_url": identity_url,
                "source_revision": identity_revision,
                "snapshot_sha256": identity_hash,
                "license": "CC0 1.0",
            },
            "identity_resolution_basis": (
                "same_film_wikidata_cast_target" if same_film_match
                else row["actor_identity_match"]
            ),
            "wikidata_film_identity_source": {
                "film_qid": film_qid,
                "source_url": film_capture.get("wikidata_capture_url"),
                "attribution_url": film_capture.get("wikidata_attribution_url"),
                "source_revision": film_capture.get("wikidata_revision"),
                "snapshot_sha256": film_capture.get("wikidata_sha256"),
                "license": film_capture.get("wikidata_license"),
            },
            "wikidata_cast_statement_locators": identity_locators,
            "wikidata_film_cast_evidence": ({
                "film_qid": film_qid,
                "source_url": film_capture.get("wikidata_capture_url"),
                "attribution_url": film_capture.get("wikidata_attribution_url"),
                "source_revision": film_capture.get("wikidata_revision"),
                "snapshot_sha256": film_capture.get("wikidata_sha256"),
                "license": film_capture.get("wikidata_license"),
                "statement_references": [
                    {
                        "statement_locator": reference["statement_locator"],
                        "source_revision": reference["source_revision"],
                        "snapshot_sha256": reference["source_sha256"],
                    }
                    for reference in matching_references
                ],
            } if same_film_match else None),
            "matching_character_qids_by_label_only": row.get("matching_wikidata_character_qids", []),
        }
        statement_digest = statement_digest_for_fields(
            source_property=SOURCE_PROPERTY, extractor_version=EXTRACTOR_VERSION,
            raw_subject=raw_subject,
            raw_value=raw_value, raw_qualifiers=raw_qualifiers,
        )
        statement_locator = f"cast-candidate/{statement_digest}"
        key = (snapshot_hash, statement_locator)
        if key in seen_locators:
            raise ValueError("Candidate report contains a duplicate source statement")
        seen_locators.add(key)
        statements.append({
            "source_property": SOURCE_PROPERTY,
            "statement_locator": statement_locator,
            "extractor_version": EXTRACTOR_VERSION,
            "raw_subject": raw_subject,
            "raw_value": {**raw_value, "statement_digest": statement_digest},
            "raw_qualifiers": raw_qualifiers,
        })
        if identity_only_match:
            identity_only_drafts += 1

    statements.sort(key=lambda row: row["statement_locator"])
    return {
        "schema": SCHEMA,
        "extractor_version": EXTRACTOR_VERSION,
        "input_schema": INPUT_SCHEMA,
        "input_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "capture_manifest_sha256": capture_hash,
        "credit_target_manifest_sha256": credit_hash,
        "credit_label_checkpoint_sha256": checkpoint_hash,
        "selection_sha256": candidate_report.get("selection_sha256"),
        "operational_fact_write": False,
        "rights_decision_created": False,
        "assertions_created": False,
        "summary": {
            "candidates_seen": len(candidates),
            "source_statement_drafts": len(statements),
            "excluded": excluded,
            "all_drafts_review_required": True,
            "actor_identity_snapshot_bound": True,
            "identity_only_drafts": identity_only_drafts,
            "character_qids_are_label_matches_only": True,
        },
        "source_statement_drafts": statements,
    }
