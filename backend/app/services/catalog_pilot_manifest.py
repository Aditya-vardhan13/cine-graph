"""Pure validation rules for the frozen catalog pilot manifest."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any


_SUPPORTED_STATUSES = {
    "exact_title_year",
    "exact_alias_year",
    "ambiguous_exact_title_year",
    "ambiguous_exact_alias_year",
    "review_required_unique_imdb_crosslink",
    "review_required_no_exact_title_year",
}
_MIN_PILOT_CROSSLINK_TITLE_SCORE = 0.80


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _year_matches(candidate: dict[str, Any], year: int | None) -> bool:
    if year is None:
        return False
    values = {str(value) for value in candidate.get("release_years_from_resolved_events", [])}
    release_date = candidate.get("release_date")
    if isinstance(release_date, str) and len(release_date) >= 4:
        values.add(release_date[:4])
    return str(year) in values


def validate_pilot_manifest(
    pilot: dict[str, Any],
    csv_bytes: bytes,
    readiness_bytes: bytes,
    imdb_review_bytes: bytes | None = None,
    *,
    expected_count: int = 100,
) -> dict[str, Any]:
    """Validate frozen inputs, row correspondence, candidate states and counts.

    This checks reproducibility and structural consistency, not the truth of a
    title match, legal reuse rights, or a human identity-review decision.
    """
    if pilot.get("version") not in {"catalog-pilot-top100-v1", "catalog-pilot-top100-v2",
                                     "catalog-pilot-top100-v3", "catalog-pilot-top100-v4",
                                     "catalog-pilot-top100-v5"}:
        raise ValueError("Unsupported pilot manifest version")
    if pilot.get("candidate_csv_sha256") != _sha256(csv_bytes):
        raise ValueError("Candidate CSV fingerprint mismatch")
    if pilot.get("readiness_report_sha256") != _sha256(readiness_bytes):
        raise ValueError("Readiness report fingerprint mismatch")
    expected_review_hash = _sha256(imdb_review_bytes) if imdb_review_bytes is not None else None
    if pilot.get("imdb_review_sha256") != expected_review_hash:
        raise ValueError("IMDb review fingerprint mismatch")

    try:
        rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Candidate CSV is not valid UTF-8 CSV") from exc
    review_by_rank: dict[int, dict[str, Any]] = {}
    if imdb_review_bytes is not None:
        try:
            review_payload = json.loads(imdb_review_bytes)
            review_by_rank = {
                item["selection_rank"]: item
                for item in review_payload.get("candidates", [])
                if isinstance(item.get("selection_rank"), int)
            }
        except (UnicodeDecodeError, ValueError, AttributeError, TypeError) as exc:
            raise ValueError("IMDb review artifact is not valid JSON candidate data") from exc
    films = pilot.get("films")
    if not isinstance(films, list) or len(films) != expected_count or len(rows) < expected_count:
        raise ValueError(f"Pilot must contain exactly {expected_count} rows")
    if pilot.get("film_count") != expected_count:
        raise ValueError("Manifest film_count does not match expected count")

    status_counts: Counter[str] = Counter()
    seen_ranks: set[int] = set()
    seen_film_ids: set[str] = set()
    for rank, (item, source) in enumerate(zip(films, rows[:expected_count]), 1):
        if item.get("selection_rank") != rank or rank in seen_ranks:
            raise ValueError("Pilot ranks must be consecutive and unique from 1")
        seen_ranks.add(rank)
        title = (source.get("Series_Title") or "").strip()
        try:
            year = int(source.get("Released_Year", ""))
        except (TypeError, ValueError):
            year = None
        if item.get("input_title") != title or item.get("input_year") != year:
            raise ValueError(f"Pilot row {rank} does not match the frozen CSV input")
        status = item.get("match_status")
        if status not in _SUPPORTED_STATUSES:
            raise ValueError(f"Pilot row {rank} has unsupported identity state: {status}")
        status_counts[status] += 1
        candidates = item.get("catalog_candidates")
        if not isinstance(candidates, list):
            raise ValueError(f"Pilot row {rank} candidates must be a list")
        ids = [candidate.get("film_id") for candidate in candidates]
        if any(not isinstance(film_id, str) or not film_id for film_id in ids):
            raise ValueError(f"Pilot row {rank} contains candidate without film_id")
        if len(ids) != len(set(ids)):
            raise ValueError(f"Pilot row {rank} repeats a catalog candidate")
        for film_id in ids:
            seen_film_ids.add(film_id)

        if status in {"exact_title_year", "exact_alias_year"}:
            if len(candidates) != 1:
                raise ValueError(f"Pilot row {rank} exact match must have one candidate")
            candidate = candidates[0]
            expected_title = title if status == "exact_title_year" else candidate.get("matched_alias")
            if not isinstance(expected_title, str) or normalize_title(expected_title) != normalize_title(title):
                raise ValueError(f"Pilot row {rank} exact title/alias does not match")
            if not _year_matches(candidate, year):
                raise ValueError(f"Pilot row {rank} exact match has no matching release year")
        elif status == "ambiguous_exact_title_year" and len(candidates) < 2:
            raise ValueError(f"Pilot row {rank} ambiguous match needs multiple candidates")
        elif status == "ambiguous_exact_alias_year" and len(candidates) < 2:
            raise ValueError(f"Pilot row {rank} ambiguous alias match needs multiple candidates")
        elif status == "review_required_unique_imdb_crosslink":
            if len(candidates) != 1 or candidates[0].get("review_required") is not True:
                raise ValueError(f"Pilot row {rank} crosslink must remain uniquely review-required")
            if not candidates[0].get("imdb_id") or not candidates[0].get("identity_evidence"):
                raise ValueError(f"Pilot row {rank} crosslink lacks identifier evidence")
            review = review_by_rank.get(rank)
            matches = [
                identity
                for hit in (review or {}).get("imdb_candidates", [])
                if hit.get("title_year_match") and hit.get("tconst") == candidates[0]["imdb_id"]
                for identity in hit.get("catalog_identity_candidates", [])
                if identity.get("film_id") == candidates[0]["film_id"]
            ]
            if len(matches) != 1:
                raise ValueError(f"Pilot row {rank} crosslink is not uniquely supported by its review artifact")
        elif status == "review_required_no_exact_title_year" and candidates:
            raise ValueError(f"Pilot row {rank} without exact match cannot select candidates")

    recorded_counts = pilot.get("match_counts")
    if recorded_counts != dict(sorted(status_counts.items())):
        raise ValueError("Manifest match_counts do not match row identity states")
    return {
        "valid": True,
        "film_count": len(films),
        "identity_state_counts": dict(sorted(status_counts.items())),
        "unique_catalog_candidate_count": len(seen_film_ids),
        "candidate_csv_sha256": _sha256(csv_bytes),
        "readiness_report_sha256": _sha256(readiness_bytes),
        "imdb_review_sha256": expected_review_hash,
        "caution": "Structural reproducibility does not prove identity truth, rights, or human review.",
    }


def adjudicate_pilot_crosslinks(
    pilot: dict[str, Any],
    pilot_bytes: bytes,
    imdb_review: dict[str, Any],
    imdb_review_bytes: bytes,
    identity_evidence: dict[str, Any],
    identity_evidence_bytes: bytes,
) -> dict[str, Any]:
    """Record narrow pilot-membership decisions from two independent ID links.

    This deliberately does not change the frozen candidate manifest, merge
    catalog entities, or authorize reuse of non-commercial IMDb fields.
    """
    pilot_hash = _sha256(pilot_bytes)
    review_hash = _sha256(imdb_review_bytes)
    evidence_hash = _sha256(identity_evidence_bytes)
    if identity_evidence.get("pilot_sha256") != pilot_hash:
        raise ValueError("Identity evidence does not bind to the supplied pilot bytes")
    if pilot.get("imdb_review_sha256") != review_hash:
        raise ValueError("Pilot does not bind to the supplied IMDb review bytes")

    review_candidates = imdb_review.get("candidates", [])
    if not isinstance(review_candidates, list):
        raise ValueError("IMDb review candidates must be a list")
    review_rows = {row.get("selection_rank"): row
                   for row in review_candidates
                   if isinstance(row, dict) and isinstance(row.get("selection_rank"), int)}
    if len(review_rows) != len(review_candidates):
        raise ValueError("IMDb review artifact contains duplicate or invalid selection ranks")
    evidence_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in identity_evidence.get("candidates", []):
        if isinstance(row, dict) and isinstance(row.get("selection_rank"), int):
            evidence_rows[row["selection_rank"]].append(row)

    decisions = []
    for film in pilot.get("films", []):
        if film.get("match_status") != "review_required_unique_imdb_crosslink":
            continue
        rank = film.get("selection_rank")
        candidates = film.get("catalog_candidates")
        if not isinstance(rank, int) or not isinstance(candidates, list) or len(candidates) != 1:
            raise ValueError("A pilot crosslink must have one ranked catalog candidate")
        candidate = candidates[0]
        if candidate.get("review_required") is not True:
            raise ValueError(f"Pilot crosslink {rank} lost its review-required source state")
        film_id = candidate.get("film_id")
        qid = candidate.get("wikidata_id")
        imdb_id = candidate.get("imdb_id")
        if not all(isinstance(value, str) and value for value in (film_id, qid, imdb_id)):
            raise ValueError(f"Pilot crosslink {rank} is missing a stable identifier")

        review = review_rows.get(rank)
        matches = [hit for hit in (review or {}).get("imdb_candidates", [])
                   if hit.get("tconst") == imdb_id and hit.get("title_year_match") is True
                   and hit.get("year") == film.get("input_year")
                   and isinstance(hit.get("score"), (float, int))
                   and not isinstance(hit.get("score"), bool)
                   and math.isfinite(hit["score"])
                   and hit["score"] >= _MIN_PILOT_CROSSLINK_TITLE_SCORE]
        if len(matches) != 1:
            raise ValueError(f"Pilot crosslink {rank} lacks one sufficiently strong title/year IMDb candidate")
        identity_matches = [item for item in matches[0].get("catalog_identity_candidates", [])
                            if item.get("film_id") == film_id and item.get("wikidata_id") == qid]
        if len(identity_matches) != 1:
            raise ValueError(f"Pilot crosslink {rank} does not map uniquely to its catalog film/QID")

        evidence_matches = [item for item in evidence_rows.get(rank, [])
                            if item.get("film_id") == film_id
                            and item.get("wikidata_id") == qid
                            and item.get("imdb_id") == imdb_id
                            and item.get("input_title") == film.get("input_title")
                            and item.get("input_year") == film.get("input_year")
                            and item.get("evidence_status") == "resolved_wikidata_p345"]
        if len(evidence_matches) != 1:
            raise ValueError(f"Pilot crosslink {rank} lacks one resolved Wikidata P345 evidence record")
        p345 = [ref for ref in evidence_matches[0].get("evidence", [])
                if ref.get("source") == "Wikidata"
                and ref.get("source_property") == "P345"
                and ref.get("raw_value_matches") is True
                and ref.get("review_status") == "resolved"
                and ref.get("license") == "CC0 1.0"
                and ref.get("attributed") is True
                and isinstance(ref.get("assertion_id"), str)
                and isinstance(ref.get("source_assertion_id"), str)
                and isinstance(ref.get("source_revision"), str)
                and ref.get("source_url") == f"https://www.wikidata.org/wiki/{qid}"]
        if not p345:
            raise ValueError(f"Pilot crosslink {rank} has no eligible, matching P345 source assertion")

        decisions.append({
            "selection_rank": rank,
            "input_title": film["input_title"],
            "input_year": film["input_year"],
            "film_id": film_id,
            "catalog_title": candidate.get("title"),
            "wikidata_id": qid,
            "imdb_id": imdb_id,
            "resolver_title": matches[0].get("title"),
            "resolver_title_year_score": matches[0]["score"],
            "decision": "accepted_same_work_for_pilot_membership_only",
            "basis": [
                "one unique title/year candidate above the resolver threshold in the pinned local IMDb review artifact",
                "the candidate IMDb ID uniquely maps to this catalog film and Wikidata QID",
                "a resolved, attributed Wikidata P345 source assertion matches that IMDb ID",
            ],
            "evidence_assertion_ids": sorted({ref["assertion_id"] for ref in p345
                                               if isinstance(ref.get("assertion_id"), str)}),
            "operational_identity_merged": False,
            "source_fields_authorized_for_product": False,
        })

    if len(decisions) != identity_evidence.get("crosslinks"):
        raise ValueError("Decision count does not match the identity evidence crosslink count")
    return {
        "version": "catalog-pilot-identity-decisions-v1",
        "scope": "pilot membership only; no catalog identity merge and no IMDb field reuse",
        "input_sha256": {
            "pilot": pilot_hash,
            "imdb_review": review_hash,
            "identity_evidence": evidence_hash,
        },
        "decision_count": len(decisions),
        "decisions": decisions,
        "caution": (
            "Decisions resolve selection-list membership only. They are not a legal clearance, "
            "a source-field approval, or a publication of IMDb data. The frozen pilot keeps its "
            "original review-required states and operational catalog entities are not merged."
        ),
    }
