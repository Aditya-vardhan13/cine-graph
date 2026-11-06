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


SCHEMA = "cinegraph.wikipedia-cast-source-statements/v1"
INPUT_SCHEMA = "cinegraph.wikipedia-cast-candidates/v7"
EXTRACTOR_VERSION = "wikipedia-cast-candidate-source-statement-v1"
SOURCE_PROPERTY = "wikipedia_cast_credit_candidate"
_QID = re.compile(r"^Q[1-9][0-9]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def _candidate_identity(candidate: dict[str, Any]) -> tuple[str, str]:
    identity = {
        "film_qid": candidate["film_qid"],
        "actor_qid": candidate["actor_qid"],
        "character": _normalized(candidate["character_name_in_source"]),
        "source_revision": candidate["wikipedia_revision"],
        "passage_sha256": candidate["passage_sha256"],
        "evidence_phrase": candidate["evidence_phrase"],
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(encoded).hexdigest()
    return digest, f"cast-candidate/{digest}"


def build_source_statement_manifest(candidate_report: dict[str, Any], report_bytes: bytes) -> dict[str, Any]:
    """Create review-only statement drafts from exact same-film cast identities.

    Candidate rows that only have an identity suggestion, an ambiguous actor,
    or a string-only character-label match are excluded from statement drafts.
    They remain counted in the report summary for a future review queue.
    """
    if candidate_report.get("schema") != INPUT_SCHEMA:
        raise ValueError("Expected the v7 retained Wikipedia cast candidate report")
    candidates = candidate_report.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("Candidate report must contain a candidates array")

    statements: list[dict[str, Any]] = []
    excluded = {"not_same_film_cast_identity": 0, "invalid_or_incomplete": 0}
    seen_locators: set[tuple[str, str]] = set()
    for row in candidates:
        if not isinstance(row, dict):
            raise ValueError("Candidate rows must be objects")
        actor_qid = row.get("actor_qid")
        if (not isinstance(actor_qid, str) or not _QID.fullmatch(actor_qid)
                or row.get("actor_identity_qid") != actor_qid
                or row.get("identity_resolution") != "same_film_wikidata_cast_target"
                or row.get("actor_identity_match") != "same_film_wikidata_cast_target"):
            excluded["not_same_film_cast_identity"] += 1
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
        if _normalized(actor_label) != _normalized(str(row.get("actor_label") or "")):
            excluded["invalid_or_incomplete"] += 1
            continue

        statement_digest, statement_locator = _candidate_identity(row)
        key = (snapshot_hash, statement_locator)
        if key in seen_locators:
            raise ValueError("Candidate report contains a duplicate source statement")
        seen_locators.add(key)
        statements.append({
            "source_property": SOURCE_PROPERTY,
            "statement_locator": statement_locator,
            "extractor_version": EXTRACTOR_VERSION,
            "raw_subject": {"film_qid": film_qid, "actor_qid": actor_qid},
            "raw_value": {
                "actor_label_in_source": actor_label,
                "character_name_in_source": character,
                "review_status": "review_required",
                "statement_digest": statement_digest,
            },
            "raw_qualifiers": {
                "wikipedia_url": source_url,
                "wikipedia_revision": revision,
                "wikipedia_snapshot_sha256": snapshot_hash,
                "wikipedia_license": "CC BY-SA 4.0",
                "attribution_url": source_url,
                "section_locator": locator,
                "passage_ordinal": ordinal,
                "passage_sha256": passage_hash,
                "evidence_phrase": phrase,
                "wikidata_cast_statement_locators": row.get("actor_statement_locators", []),
                "matching_character_qids_by_label_only": row.get("matching_wikidata_character_qids", []),
            },
        })

    statements.sort(key=lambda row: row["statement_locator"])
    return {
        "schema": SCHEMA,
        "extractor_version": EXTRACTOR_VERSION,
        "input_schema": INPUT_SCHEMA,
        "input_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "selection_sha256": candidate_report.get("selection_sha256"),
        "operational_fact_write": False,
        "rights_decision_created": False,
        "assertions_created": False,
        "summary": {
            "candidates_seen": len(candidates),
            "source_statement_drafts": len(statements),
            "excluded": excluded,
            "all_drafts_review_required": True,
            "character_qids_are_label_matches_only": True,
        },
        "source_statement_drafts": statements,
    }
