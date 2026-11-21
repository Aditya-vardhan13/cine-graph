"""Pure admission accounting for immutable corpus-build input manifests."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def manifest_source(*, snapshot_id: str, snapshot_hash: str, source_url: str,
                    revision: str | None, fetch_status: str, integrity: str, semantic_approved: bool,
                    passages: list[dict]) -> dict:
    ordered = sorted(passages, key=lambda row: (row["section"], row["ordinal"], row["id"]))
    failures = []
    if fetch_status != "success":
        failures.append("snapshot_fetch_status:" + str(fetch_status))
    if integrity != "verified":
        failures.append("snapshot_integrity:" + integrity)
    if not semantic_approved:
        failures.append("semantic_use_not_approved")
    if not ordered:
        failures.append("no_current_passages")
    if any(not row["hash_verified"] for row in ordered):
        failures.append("passage_hash_mismatch")
    return {
        "snapshot_id": snapshot_id, "snapshot_sha256": snapshot_hash,
        "source_url": source_url, "revision": revision, "fetch_status": fetch_status, "integrity": integrity,
        "semantic_approved": semantic_approved, "passages": ordered,
        "build_eligible": not failures, "exclusion_reasons": failures,
    }


def finalize_manifest(collection: str, films: list[dict]) -> dict:
    films = sorted(films, key=lambda film: film["entity_id"])
    if len({film["entity_id"] for film in films}) != len(films):
        raise ValueError("duplicate_film_entity")
    payload = {"schema": "cinegraph.corpus-build-input/v2", "collection": collection,
               "identity_review_performed": False,
               "note": "Readiness inventory, not film identity approval or an activated index.",
               "films": films}
    return {**payload, "manifest_sha256": canonical_digest(payload)}
