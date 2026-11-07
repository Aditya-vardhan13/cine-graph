"""Pure checks for candidate-to-captured-Wikipedia-passage bindings."""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any

from app.services.wikipedia_cast_candidates import CAST_SECTION_NAMES


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def passage_binding_errors(candidate: dict[str, Any], film: dict[str, Any], passage: dict[str, Any]) -> list[str]:
    """Return source-binding failures without deciding whether a credit is true."""
    errors: list[str] = []
    if candidate.get("film_qid") != film.get("qid"):
        errors.append("film_qid_mismatch")
    if candidate.get("selection_rank") != film.get("selection_rank"):
        errors.append("selection_rank_mismatch")
    if candidate.get("film_title") != film.get("title"):
        errors.append("film_title_mismatch")
    if "film_year" in candidate and candidate.get("film_year") != film.get("year"):
        errors.append("film_year_mismatch")
    if candidate.get("wikipedia_url") != film.get("wikipedia_attribution_url"):
        errors.append("article_url_mismatch")
    if candidate.get("wikipedia_revision") != film.get("wikipedia_revision"):
        errors.append("article_revision_mismatch")
    if candidate.get("wikipedia_snapshot_sha256") != film.get("wikipedia_sha256"):
        errors.append("article_hash_mismatch")
    if ("wikipedia_license" in candidate
            and candidate.get("wikipedia_license") != film.get("wikipedia_license")):
        errors.append("article_license_mismatch")
    section_locator = candidate.get("section_locator")
    if (not isinstance(section_locator, str)
            or not any(part in CAST_SECTION_NAMES for part in section_locator.casefold().split("/"))):
        errors.append("candidate_outside_cast_section")
    if candidate.get("section_locator") != passage.get("section_locator"):
        errors.append("passage_section_mismatch")
    if candidate.get("section_title") != passage.get("section_title"):
        errors.append("passage_section_title_mismatch")
    if candidate.get("passage_ordinal") != passage.get("ordinal"):
        errors.append("passage_ordinal_mismatch")
    content = passage.get("content")
    if not isinstance(content, str) or candidate.get("passage_sha256") != sha256(content.encode("utf-8")):
        errors.append("passage_hash_mismatch")
    phrase = candidate.get("evidence_phrase")
    if not isinstance(phrase, str) or not phrase.strip() or not isinstance(content, str) or phrase not in content:
        errors.append("evidence_phrase_not_in_passage")
    return errors


def candidate_audit_summary(
    *,
    capture_manifest_sha256: str,
    candidate_report_sha256: str,
    films: int,
    snapshots_verified: int,
    passage_derivatives_verified: int,
    candidate_rows: int,
    candidate_rows_verified: int,
    quarantined_rows: int,
    quarantined_rows_verified: int,
    error_counts: Counter[str],
) -> dict[str, Any]:
    """Create a compact, passage-text-free audit summary."""
    return {
        "capture_manifest_sha256": capture_manifest_sha256,
        "candidate_report_sha256": candidate_report_sha256,
        "films": films,
        "article_snapshots_verified": snapshots_verified,
        "passage_derivatives_verified": passage_derivatives_verified,
        "candidate_rows": candidate_rows,
        "candidate_source_bindings_verified": candidate_rows_verified,
        "quarantined_rows": quarantined_rows,
        "quarantined_source_bindings_verified": quarantined_rows_verified,
        "error_counts": dict(sorted(error_counts.items())),
        "status": "passed" if not error_counts else "failed",
    }
