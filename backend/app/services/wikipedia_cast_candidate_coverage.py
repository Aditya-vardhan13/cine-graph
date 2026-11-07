"""Validate and combine partitioned cast-candidate reports for a fixed pilot."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from app.services.wikipedia_cast_source_statements import (
    EXTRACTOR_VERSION,
    SOURCE_PROPERTY,
    statement_digest_for_fields,
)
from app.services.wikipedia_cast_statement_replay import validate_cast_source_statement_draft


CANDIDATE_SCHEMA = "cinegraph.wikipedia-cast-candidates/v8"
STATEMENT_SCHEMA = "cinegraph.wikipedia-cast-source-statements/v5"
_IDENTITY = "same_film_wikidata_cast_target"


def _candidate_statement_binding(candidate: dict[str, Any]) -> str:
    """Fingerprint the exact source/identity fields projected into a draft."""
    identity = candidate.get("actor_identity_evidence")
    identity = identity if isinstance(identity, dict) else {}

    def trimmed_text(field: str) -> Any:
        value = candidate.get(field)
        return value.strip() if isinstance(value, str) else value

    binding = {
        "raw_subject": {
            "film_qid": candidate.get("film_qid"),
            "actor_qid": candidate.get("actor_qid") or candidate.get("actor_identity_qid"),
        },
        "raw_value": {
            # The statement builder applies _text() to these fields, which
            # deliberately strips surrounding whitespace before hashing.
            "actor_label_in_source": trimmed_text("actor_label_in_source"),
            "character_name_in_source": trimmed_text("character_name_in_source"),
            "review_status": candidate.get("review_status"),
        },
        "raw_qualifiers": {
            "wikipedia_url": candidate.get("wikipedia_url"),
            "wikipedia_revision": candidate.get("wikipedia_revision"),
            "wikipedia_snapshot_sha256": candidate.get("wikipedia_snapshot_sha256"),
            "wikipedia_license": candidate.get("wikipedia_license"),
            "attribution_url": candidate.get("wikipedia_url"),
            "section_locator": candidate.get("section_locator"),
            "passage_ordinal": candidate.get("passage_ordinal"),
            "passage_sha256": candidate.get("passage_sha256"),
            "evidence_phrase": trimmed_text("evidence_phrase"),
            "wikidata_actor_identity": {
                "entity_qid": candidate.get("actor_identity_qid"),
                "entity_label": candidate.get("actor_identity_label"),
                "source_url": identity.get("source_url"),
                "source_revision": identity.get("source_revision"),
                "snapshot_sha256": identity.get("snapshot_sha256"),
                "license": "CC0 1.0",
            },
            "wikidata_cast_statement_locators": candidate.get("actor_statement_locators"),
            "identity_resolution_basis": candidate.get("actor_identity_match"),
            "matching_character_qids_by_label_only": candidate.get(
                "matching_wikidata_character_qids", []
            ),
        },
    }
    return json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _draft_statement_binding(draft: dict[str, Any]) -> str:
    value = draft.get("raw_value")
    qualifiers = draft.get("raw_qualifiers")
    subject = draft.get("raw_subject")
    value = value if isinstance(value, dict) else {}
    qualifiers = qualifiers if isinstance(qualifiers, dict) else {}
    subject = subject if isinstance(subject, dict) else {}
    binding = {
        "raw_subject": {
            "film_qid": subject.get("film_qid"),
            "actor_qid": subject.get("actor_qid"),
        },
        "raw_value": {
            "actor_label_in_source": value.get("actor_label_in_source"),
            "character_name_in_source": value.get("character_name_in_source"),
            "review_status": value.get("review_status"),
        },
        "raw_qualifiers": {
            field: qualifiers.get(field)
            for field in (
                "wikipedia_url", "wikipedia_revision", "wikipedia_snapshot_sha256",
                "wikipedia_license", "attribution_url", "section_locator",
                "passage_ordinal", "passage_sha256", "evidence_phrase",
                "wikidata_actor_identity", "wikidata_cast_statement_locators",
                "identity_resolution_basis",
                "matching_character_qids_by_label_only",
            )
        },
    }
    return json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _required_list(value: Any, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def build_cast_candidate_coverage(
    candidate_inputs: list[tuple[dict[str, Any], bytes]],
    statement_inputs: list[tuple[dict[str, Any], bytes]],
    pilot_input: tuple[dict[str, Any], bytes],
    *, expected_film_count: int = 100,
) -> dict[str, Any]:
    """Join disjoint candidate partitions and their exact-input statement bundles.

    The join is intentionally strict: all partitions must describe one frozen
    pilot; identities must be unique, each row must bind to the partition's
    retained source revision, and statement manifests must hash the exact
    candidate-report bytes. Partition fingerprints may differ because captures
    can be split; the frozen pilot manifest is the cross-partition authority.
    This is coverage QA, not credit verification.
    """
    if expected_film_count < 1:
        raise ValueError("Expected film count must be positive")
    if not candidate_inputs or len(candidate_inputs) != len(statement_inputs):
        raise ValueError("Each candidate report requires exactly one statement manifest")

    pilot, pilot_bytes = pilot_input
    pilot_films = _required_list(pilot.get("films"), "Frozen pilot films")
    if pilot.get("film_count") != expected_film_count or len(pilot_films) != expected_film_count:
        raise ValueError("Frozen pilot manifest does not match the expected film count")
    pilot_by_rank: dict[int, dict[str, Any]] = {}
    for item in pilot_films:
        if not isinstance(item, dict):
            raise ValueError("Frozen pilot film rows must be objects")
        rank = item.get("selection_rank")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank in pilot_by_rank:
            raise ValueError("Frozen pilot ranks must be unique integers")
        # The frozen catalog-pilot manifest keeps candidate identities nested
        # under catalog_candidates. Accept that authoritative form only when
        # it contains exactly one candidate; never choose among ambiguities.
        pilot_identity = item.get("wikidata_id")
        if pilot_identity is None:
            catalog_candidates = item.get("catalog_candidates")
            if (not isinstance(catalog_candidates, list) or len(catalog_candidates) != 1
                    or not isinstance(catalog_candidates[0], dict)):
                raise ValueError("Frozen pilot film must resolve to exactly one catalog identity")
            pilot_identity = catalog_candidates[0].get("wikidata_id")
        if not isinstance(pilot_identity, str) or not re.fullmatch(r"Q[1-9][0-9]*", pilot_identity):
            raise ValueError("Frozen pilot film lacks a canonical Wikidata ID")
        pilot_by_rank[rank] = {**item, "wikidata_id": pilot_identity}
    if sorted(pilot_by_rank) != list(range(1, expected_film_count + 1)):
        raise ValueError("Frozen pilot ranks must cover the expected range")

    statements_by_input: dict[str, dict[str, Any]] = {}
    statement_manifest_hashes: list[str] = []
    for manifest, raw in statement_inputs:
        if manifest.get("schema") != STATEMENT_SCHEMA:
            raise ValueError("Unexpected cast source-statement schema")
        if manifest.get("operational_fact_write") is not False or manifest.get("assertions_created") is not False:
            raise ValueError("Coverage audit accepts only review-only statement manifests")
        input_hash = manifest.get("input_sha256")
        if not isinstance(input_hash, str) or len(input_hash) != 64:
            raise ValueError("Statement manifest has no valid candidate input hash")
        if input_hash in statements_by_input:
            raise ValueError("Multiple statement manifests claim the same candidate report")
        statements_by_input[input_hash] = manifest
        statement_manifest_hashes.append(_sha256(raw))
        selection = manifest.get("selection_sha256")
        if not isinstance(selection, str) or len(selection) != 64:
            raise ValueError("Statement manifest has no frozen selection fingerprint")

    films_by_rank: dict[int, dict[str, Any]] = {}
    films_by_qid: dict[str, dict[str, Any]] = {}
    candidate_count = 0
    identity_count = 0
    identity_suggestion_count = 0
    unresolved_count = 0
    character_label_match_count = 0
    quarantine_reasons: Counter[str] = Counter()
    statement_count = 0
    candidate_report_hashes: list[str] = []
    all_statement_locators: set[str] = set()
    candidate_statement_bindings: Counter[str] = Counter()
    draft_statement_bindings: Counter[str] = Counter()

    candidate_selections: set[str] = set()
    matched_statement_inputs: set[str] = set()
    for report, raw in candidate_inputs:
        if report.get("schema") != CANDIDATE_SCHEMA:
            raise ValueError("Unexpected Wikipedia cast-candidate report schema")
        selection = report.get("selection_sha256")
        if not isinstance(selection, str) or len(selection) != 64:
            raise ValueError("Candidate report has no frozen selection fingerprint")
        candidate_selections.add(selection)
        if report.get("operational_fact_write") is not False:
            raise ValueError("Candidate report must not write operational facts")

        raw_hash = _sha256(raw)
        candidate_report_hashes.append(raw_hash)
        statement_manifest = statements_by_input.get(raw_hash)
        if statement_manifest is None:
            raise ValueError("No statement manifest is bound to exact candidate-report bytes")
        matched_statement_inputs.add(raw_hash)
        if statement_manifest.get("selection_sha256") != selection:
            raise ValueError("Candidate and statement manifests have different frozen selections")
        if statement_manifest.get("input_schema") != CANDIDATE_SCHEMA:
            raise ValueError("Statement manifest records a different candidate input schema")
        if (statement_manifest.get("capture_manifest_sha256")
                != report.get("film_capture_manifest_sha256")
                or statement_manifest.get("credit_target_manifest_sha256")
                != report.get("credit_target_manifest_sha256")
                or statement_manifest.get("credit_label_checkpoint_sha256")
                != report.get("credit_label_checkpoint_sha256")):
            raise ValueError("Statement manifest is not bound to the candidate's exact Wikidata capture, targets and person-label checkpoint")

        report_films = _required_list(report.get("films"), "Candidate report films")
        candidates = _required_list(report.get("candidates"), "Candidate rows")
        ambiguities = _required_list(report.get("ambiguities"), "Quarantined candidates")
        summary = report.get("summary")
        if not isinstance(summary, dict) or summary.get("films") != len(report_films):
            raise ValueError("Candidate summary film count does not match its rows")
        if summary.get("candidate_rows") != len(candidates):
            raise ValueError("Candidate summary count does not match candidate rows")
        if summary.get("ambiguous_or_unmatched_rows") != len(ambiguities):
            raise ValueError("Candidate summary count does not match quarantined rows")

        before_counts = (candidate_count, identity_count, identity_suggestion_count,
                         unresolved_count, character_label_match_count)
        before_quarantines = sum(quarantine_reasons.values())
        report_rank_rows: dict[int, dict[str, Any]] = {}
        for film in report_films:
            if not isinstance(film, dict):
                raise ValueError("Candidate film rows must be objects")
            rank, qid = film.get("selection_rank"), film.get("film_qid")
            if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
                raise ValueError("Candidate film rank must be a positive integer")
            if not isinstance(qid, str) or not qid.startswith("Q"):
                raise ValueError("Candidate film row lacks a Wikidata QID")
            if rank in films_by_rank or qid in films_by_qid:
                raise ValueError("Candidate partitions repeat a rank or film QID")
            pilot_film = pilot_by_rank.get(rank)
            if pilot_film is None or qid != pilot_film.get("wikidata_id"):
                raise ValueError("Candidate film identity does not match the frozen pilot rank")
            if (film.get("title") != pilot_film.get("input_title")
                    or film.get("year") != pilot_film.get("input_year")):
                raise ValueError("Candidate film title/year does not match the frozen pilot rank")
            row = {
                "selection_rank": rank,
                "film_qid": qid,
                "title": film.get("title"),
                "year": film.get("year"),
                "wikipedia_revision": film.get("source_revision"),
                "wikipedia_snapshot_sha256": film.get("source_sha256"),
                "cast_passages": film.get("cast_passages"),
                "_reported_candidate_count": film.get("candidate_count"),
                "_reported_quarantine_count": film.get("ambiguous_or_unmatched_count"),
                "candidate_count": 0,
                "same_film_identity_candidates": 0,
                "identity_only_suggestions": 0,
                "unresolved_source_names": 0,
                "character_label_matches_only": 0,
                "quarantined_spans": 0,
                "source_statement_drafts": 0,
                "quarantine_reasons": {},
                "wikipedia_url": None,
            }
            films_by_rank[rank] = row
            films_by_qid[qid] = row
            report_rank_rows[rank] = film

        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError("Candidate rows must be objects")
            rank = candidate.get("selection_rank")
            row = films_by_rank.get(rank)
            if row is None or rank not in report_rank_rows:
                raise ValueError("Candidate row points outside its partition's film list")
            source_film = report_rank_rows[rank]
            if any((candidate.get("film_qid") != source_film.get("film_qid"),
                    candidate.get("film_title") != source_film.get("title"),
                    candidate.get("film_year") != source_film.get("year"),
                    candidate.get("wikipedia_revision") != source_film.get("source_revision"),
                    candidate.get("wikipedia_snapshot_sha256") != source_film.get("source_sha256"))):
                raise ValueError("Candidate row is not bound to its film's retained source revision")
            if candidate.get("review_status") != "review_required":
                raise ValueError("Candidate rows must remain review_required")
            url = candidate.get("wikipedia_url")
            if not isinstance(url, str) or not url.startswith("https://en.wikipedia.org/wiki/"):
                raise ValueError("Candidate row lacks an English Wikipedia article URL")
            if row["wikipedia_url"] not in (None, url):
                raise ValueError("One film is bound to multiple Wikipedia URLs")
            row["wikipedia_url"] = url
            row["candidate_count"] += 1
            candidate_count += 1
            resolution = candidate.get("identity_resolution")
            if resolution == _IDENTITY:
                row["same_film_identity_candidates"] += 1
                identity_count += 1
                candidate_statement_bindings[_candidate_statement_binding(candidate)] += 1
            elif resolution == "matched_captured_person_identity_only":
                row["identity_only_suggestions"] += 1
                identity_suggestion_count += 1
                candidate_statement_bindings[_candidate_statement_binding(candidate)] += 1
            elif resolution == "unresolved_source_name":
                row["unresolved_source_names"] += 1
                unresolved_count += 1
            else:
                raise ValueError(f"Unknown candidate identity state: {resolution!r}")
            if candidate.get("matching_wikidata_character_qids"):
                row["character_label_matches_only"] += 1
                character_label_match_count += 1

        for item in ambiguities:
            if not isinstance(item, dict):
                raise ValueError("Quarantined candidate rows must be objects")
            row = films_by_rank.get(item.get("selection_rank"))
            if row is None or item.get("film_qid") != row["film_qid"]:
                raise ValueError("Quarantined row points outside its partition's film list")
            reason = item.get("reason")
            if not isinstance(reason, str) or not reason:
                raise ValueError("Quarantined row has no reason")
            row["quarantined_spans"] += 1
            quarantine_reasons[reason] += 1
            row["quarantine_reasons"][reason] = row["quarantine_reasons"].get(reason, 0) + 1

        if summary.get("films_with_candidates") != sum(
            films_by_rank[rank]["candidate_count"] > 0 for rank in report_rank_rows
        ):
            raise ValueError("Candidate summary films_with_candidates does not match its rows")
        if summary.get("films_with_cast_passages") != sum(bool(row.get("cast_passages")) for row in report_films):
            raise ValueError("Candidate summary films_with_cast_passages does not match its rows")

        actual_counts = {
            "candidate_rows": candidate_count - before_counts[0],
            "wikidata_actor_candidates": identity_count - before_counts[1],
            "source_only_identity_matches": identity_suggestion_count - before_counts[2],
            "source_only_unresolved_candidates": unresolved_count - before_counts[3],
            "candidates_matching_wikidata_character_label": character_label_match_count - before_counts[4],
            "ambiguous_or_unmatched_rows": sum(quarantine_reasons.values()) - before_quarantines,
        }
        for field, count in actual_counts.items():
            if summary.get(field) != count:
                raise ValueError(f"Candidate report summary {field} does not match its rows")

    if matched_statement_inputs != set(statements_by_input):
        raise ValueError("One or more statement manifests are not bound to an input candidate report")
    expected = list(range(1, expected_film_count + 1))
    if sorted(films_by_rank) != expected or len(films_by_qid) != expected_film_count:
        raise ValueError("Candidate partitions must cover each expected rank exactly once")

    for manifest in statements_by_input.values():
        drafts = _required_list(manifest.get("source_statement_drafts"), "Source statement drafts")
        if len(drafts) != manifest.get("summary", {}).get("source_statement_drafts"):
            raise ValueError("Statement summary does not match its draft rows")
        for draft in drafts:
            if not isinstance(draft, dict):
                raise ValueError("Source statement drafts must be objects")
            subject, qualifiers = draft.get("raw_subject"), draft.get("raw_qualifiers")
            if not isinstance(subject, dict) or not isinstance(qualifiers, dict):
                raise ValueError("Source statement draft lacks subject or provenance")
            value = draft.get("raw_value")
            if (draft.get("source_property") != SOURCE_PROPERTY
                    or draft.get("extractor_version") != EXTRACTOR_VERSION
                    or not isinstance(value, dict)
                    or value.get("review_status") != "review_required"):
                raise ValueError("Source statement draft is not a supported review-only cast statement")
            validate_cast_source_statement_draft(draft)
            draft_statement_bindings[_draft_statement_binding(draft)] += 1
            digest = statement_digest_for_fields(
                source_property=SOURCE_PROPERTY,
                extractor_version=draft["extractor_version"],
                raw_subject=subject,
                raw_value=value,
                raw_qualifiers=qualifiers,
            )
            if (value.get("statement_digest") != digest
                    or draft.get("statement_locator") != f"cast-candidate/{digest}"):
                raise ValueError("Source statement content does not match its content-addressed locator")
            row = films_by_qid.get(subject.get("film_qid"))
            if row is None:
                raise ValueError("Source statement points outside the selected film set")
            if (qualifiers.get("wikipedia_snapshot_sha256") != row["wikipedia_snapshot_sha256"]
                    or qualifiers.get("wikipedia_revision") != row["wikipedia_revision"]
                    or qualifiers.get("wikipedia_url") != row["wikipedia_url"]):
                raise ValueError("Source statement is not bound to the selected film's retained article")
            locator = draft.get("statement_locator")
            if not isinstance(locator, str) or locator in all_statement_locators:
                raise ValueError("Source statement locators must be unique across partitions")
            all_statement_locators.add(locator)
            row["source_statement_drafts"] += 1
            statement_count += 1

    for row in films_by_rank.values():
        if row["candidate_count"] != row.pop("_reported_candidate_count"):
            raise ValueError("Per-film candidate count does not match its report summary")
        if row["quarantined_spans"] != row.pop("_reported_quarantine_count"):
            raise ValueError("Per-film quarantine count does not match its report summary")
        if row["source_statement_drafts"] != (
            row["same_film_identity_candidates"] + row["identity_only_suggestions"]
        ):
            raise ValueError("Strong-identity candidates and exact-source drafts are not one-to-one")

    if candidate_statement_bindings != draft_statement_bindings:
        raise ValueError("Source statement drafts do not match their exact candidate evidence rows")

    return {
        "schema": "cinegraph.wikipedia-cast-candidate-coverage/v1",
        "pilot_manifest_sha256": _sha256(pilot_bytes),
        "partition_selection_sha256": sorted(candidate_selections),
        "input_report_sha256": candidate_report_hashes,
        "statement_manifest_sha256": statement_manifest_hashes,
        "summary": {
            "films": expected_film_count,
            "candidate_rows": candidate_count,
            "same_film_identity_candidates": identity_count,
            "identity_only_candidates_with_review_drafts": identity_suggestion_count,
            "review_only_source_statement_drafts": statement_count,
            "identity_only_suggestions": identity_suggestion_count,
            "unresolved_source_names": unresolved_count,
            "character_label_matches_only": character_label_match_count,
            "quarantined_spans": sum(quarantine_reasons.values()),
            "quarantine_reasons": dict(sorted(quarantine_reasons.items())),
            "all_candidates_review_required": True,
            "actor_character_credits_verified": False,
            "operational_assertions_written": False,
        },
        "films": [films_by_rank[rank] for rank in expected],
        "limitations": [
            "Coverage is extraction and identity resolution only; candidates are not verified credits.",
            "Character QID label matches are suggestions, not actor-character evidence.",
            "Review-only source statements are not operational assertions or rights decisions.",
        ],
    }


def render_cast_candidate_coverage(report: dict[str, Any]) -> str:
    """Render a source-linked, passage-free human audit sheet."""
    summary = report["summary"]
    lines = [
        "# Wikipedia cast-candidate coverage — English 100-film pilot",
        "",
        "> This report measures extraction and identity binding, not correct or complete credits. Every candidate requires review; character-name matches are label-only suggestions.",
        "",
        f"- Films: **{summary['films']}**",
        f"- Candidate rows: **{summary['candidate_rows']}**; same-film actor identity candidates: **{summary['same_film_identity_candidates']}**",
        f"- Review-only source-statement drafts: **{summary['review_only_source_statement_drafts']}**",
        f"- Identity-only suggestions: **{summary['identity_only_suggestions']}**; drafts created for those suggestions: **{summary['identity_only_candidates_with_review_drafts']}**; unresolved names: **{summary['unresolved_source_names']}**",
        f"- Character label matches only: **{summary['character_label_matches_only']}**; quarantined spans: **{summary['quarantined_spans']}**",
        f"- Quarantine reasons: `{json.dumps(summary['quarantine_reasons'], sort_keys=True)}`",
        "",
        "## Film-by-film audit queue",
        "",
        "Open the source article at the captured revision, then review candidate wording against the exact cast passage. `same-film` means only that the actor QID is listed for the film in Wikidata; it does not verify this Wikipedia credit. `Identity suggestion` is a unique captured English label/alias match only: the retained film-side Wikidata P161 snapshot does not list that actor, so this is not cast corroboration. All `drafts` are retained source statements, still `review_required`; none are operational credits until a reviewer verifies the exact article passage.",
        "",
        "| Rank | Film | QID | Cast passages | Candidates | Same-film | Identity suggestion | Unresolved | Label-only character | Quarantined | Drafts | Captured article |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for film in report["films"]:
        title = str(film["title"]).replace("|", "\\|")
        revision_url = f"{film['wikipedia_url']}?oldid={film['wikipedia_revision']}"
        lines.append(
            f"| {film['selection_rank']} | {title} ({film['year']}) | `{film['film_qid']}` | {film['cast_passages']} | "
            f"{film['candidate_count']} | {film['same_film_identity_candidates']} | {film['identity_only_suggestions']} | "
            f"{film['unresolved_source_names']} | {film['character_label_matches_only']} | {film['quarantined_spans']} | "
            f"{film['source_statement_drafts']} | [revision {film['wikipedia_revision']}]({revision_url}) |"
        )
    lines.extend([
        "",
        "## Reproducibility",
        "",
        f"- Frozen pilot manifest SHA-256: `{report['pilot_manifest_sha256']}`",
        "- Captured partition selection fingerprints: " + ", ".join(
            f"`{value}`" for value in report["partition_selection_sha256"]
        ),
        "- Candidate report SHA-256: " + ", ".join(f"`{value}`" for value in report["input_report_sha256"]),
        "- Statement manifest SHA-256: " + ", ".join(f"`{value}`" for value in report["statement_manifest_sha256"]),
        "- No narrative passage text is reproduced in this review sheet.",
        "",
    ])
    return "\n".join(lines)
