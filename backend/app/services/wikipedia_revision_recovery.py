"""Reacquire pinned Wikipedia revisions whose original local capture is gone.

This is a manual, paced recovery job, not a replacement for the original
snapshot. The exact API response becomes a new immutable snapshot with its own
hash; existing passages and reviewed facts are never silently repointed.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DataSource, SourceAccessPolicy, SourceObject, SourceSnapshot
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.wikipedia_raw import SOURCE_NAME

ADAPTER_NAME = "wikipedia_pinned_revision_recovery"
ADAPTER_VERSION = "enwiki-pinned-revision-recovery-v1"
OLD_ROOT = "file:///private/tmp/cinegraph-pilot-raw/"


class RevisionRecoveryError(RuntimeError):
    pass


def recovery_target_is_valid(page: dict, *, revision: str, external_id: str) -> bool:
    parsed = page.get("parse")
    if not isinstance(parsed, dict):
        return False
    try:
        return (
            int(parsed.get("revid")) == int(revision)
            and int(parsed.get("pageid")) == int(external_id.removeprefix("enwiki:"))
            and isinstance(parsed.get("wikitext"), str)
            and bool(parsed["wikitext"].strip())
        )
    except (TypeError, ValueError):
        return False


def should_retry_response(status_code: int, headers: Mapping[str, str], api_error_code: str | None) -> bool:
    """Retry only explicit throttling/lag, never an unsignalled cache timeout."""
    return (
        status_code == 429
        or api_error_code in {"maxlag", "ratelimited"}
        or (status_code == 503 and bool(headers.get("Retry-After") or headers.get("X-Database-Lag")))
    )


def missing_originals(db: Session) -> list[tuple[SourceSnapshot, SourceObject]]:
    rows = db.execute(
        select(SourceSnapshot, SourceObject)
        .join(SourceObject, SourceObject.id == SourceSnapshot.source_object_id)
        .join(DataSource, DataSource.id == SourceObject.source_id)
        .where(DataSource.name == SOURCE_NAME, SourceSnapshot.storage_uri.like(f"{OLD_ROOT}%"))
        .order_by(SourceObject.external_id, SourceSnapshot.retrieved_at)
    ).all()
    return [
        (old, item) for old, item in rows
        if old.source_revision and verify_snapshot_file(old.storage_uri, old.content_hash, old.byte_size) == "missing"
    ]


def already_recovered(db: Session, old: SourceSnapshot) -> bool:
    candidates = db.scalars(select(SourceSnapshot).where(
        SourceSnapshot.source_object_id == old.source_object_id,
        SourceSnapshot.source_revision == old.source_revision,
        SourceSnapshot.parser_version == ADAPTER_VERSION,
    )).all()
    return any(verify_snapshot_file(item.storage_uri, item.content_hash, item.byte_size) == "verified" for item in candidates)


def fetch_pinned_revision(client, revision: str, external_id: str) -> bytes:
    """Legacy API recovery is disabled because current robots.txt disallows /w/."""
    raise RevisionRecoveryError(
        "Pinned Wikipedia wikitext recovery via /w/api.php is disallowed by current robots.txt. "
        "Do not run this adapter; implement an approved article-page recovery path first."
    )


def recover(db: Session, *, limit: int | None = None, execute: bool = False) -> dict[str, object]:
    source = db.scalar(select(DataSource).where(DataSource.name == SOURCE_NAME))
    if not source:
        raise RevisionRecoveryError("English Wikipedia is not registered in this database.")
    policy = db.scalar(select(SourceAccessPolicy).where(
        SourceAccessPolicy.source_id == source.id,
        SourceAccessPolicy.access_mode == "api",
    ))
    if not policy:
        raise RevisionRecoveryError("No Wikipedia access-policy record exists in this database.")
    targets: list[tuple[SourceSnapshot, SourceObject]] = []
    seen_revisions: set[tuple[object, str]] = set()
    for old, item in missing_originals(db):
        key = (old.source_object_id, old.source_revision)
        if key not in seen_revisions and not already_recovered(db, old):
            targets.append((old, item))
        seen_revisions.add(key)
    selected = targets[:limit] if limit is not None else targets
    result: dict[str, object] = {"missing_unrecovered": len(targets), "selected": len(selected), "fetched": 0, "status": "dry_run"}
    if not execute or not selected:
        return result
    result["status"] = "blocked_by_policy"
    result["error"] = (
        "Current en.wikipedia.org robots.txt disallows /w/api.php. The API recovery adapter "
        "is disabled until a permitted article-page recovery strategy is implemented."
    )
    return result


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Read-only audit and policy-gated recovery of missing Wikipedia snapshots.")
    parser.add_argument("--limit", type=int, help="Maximum number of original snapshots to reacquire.")
    parser.add_argument("--execute", action="store_true", help="Attempt recovery; currently blocked because the API route is disallowed by robots.txt.")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    with SessionLocal() as db:
        result = recover(db, limit=args.limit, execute=args.execute)
    print(json.dumps(result, indent=2))
    if result["status"] in {"failed", "blocked_by_policy"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
