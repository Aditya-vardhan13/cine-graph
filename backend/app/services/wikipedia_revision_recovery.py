"""Reacquire pinned Wikipedia revisions whose original local capture is gone.

This is a manual, paced recovery job, not a replacement for the original
snapshot. The exact API response becomes a new immutable snapshot with its own
hash; existing passages and reviewed facts are never silently repointed.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DataSource, RawIngestionRun, SourceAccessPolicy, SourceObject, SourceSnapshot
from app.services.raw_snapshots import snapshot
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.wikipedia_raw import SOURCE_NAME, WIKIPEDIA_API

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


def fetch_pinned_revision(client: httpx.Client, revision: str, external_id: str) -> bytes:
    params = {
        "action": "parse", "format": "json", "formatversion": "2", "oldid": revision,
        "prop": "wikitext", "maxlag": "5",
    }
    delay = 5.0
    for attempt in range(4):
        try:
            response = client.get(WIKIPEDIA_API, params=params)
        except httpx.TransportError as error:
            if attempt == 3:
                raise RevisionRecoveryError(
                    f"MediaWiki transport failed after bounded retries: {error}"
                ) from error
            time.sleep(delay)
            delay = min(delay * 2, 300.0)
            continue
        if response.status_code in (401, 403):
            raise RevisionRecoveryError(f"MediaWiki denied this request ({response.status_code}); stop the run.")
        api_error_code = response.json().get("error", {}).get("code") if response.status_code == 200 else None
        if should_retry_response(response.status_code, response.headers, api_error_code):
            if attempt == 3:
                raise RevisionRecoveryError(
                    f"MediaWiki remained unavailable, rate-limited or lagged after bounded retries ({response.status_code}); stop the run."
                )
            retry_after = response.headers.get("Retry-After")
            try:
                wait = max(delay, min(float(retry_after), 300.0)) if retry_after else delay
            except ValueError:
                wait = delay
            time.sleep(wait)
            delay = min(delay * 2, 300.0)
            continue
        response.raise_for_status()
        if not recovery_target_is_valid(response.json(), revision=revision, external_id=external_id):
            raise RevisionRecoveryError(f"Revision {revision} did not return the expected page, revision and wikitext.")
        return response.content
    raise RevisionRecoveryError("The revision could not be fetched.")


def _require_persistent_root() -> Path:
    root = Path(get_settings().raw_snapshot_root).expanduser().resolve()
    temp_roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve(), Path("/private/tmp").resolve()}
    if any(root == item or item in root.parents for item in temp_roots):
        raise RevisionRecoveryError(f"Recovery requires persistent snapshot storage, not a temporary directory: {root}")
    return root


def recover(db: Session, *, limit: int | None = None, execute: bool = False) -> dict[str, object]:
    source = db.scalar(select(DataSource).where(DataSource.name == SOURCE_NAME))
    if not source:
        raise RevisionRecoveryError("English Wikipedia is not registered in this database.")
    policy = db.scalar(select(SourceAccessPolicy).where(
        SourceAccessPolicy.source_id == source.id,
        SourceAccessPolicy.access_mode == "api",
        SourceAccessPolicy.decision == "allowed",
    ))
    if not policy or WIKIPEDIA_API not in policy.allowed_paths:
        raise RevisionRecoveryError("The documented Wikipedia API route has no approved access policy.")
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
    _require_persistent_root()
    run = RawIngestionRun(
        source_id=source.id, access_policy_id=policy.id, adapter_name=ADAPTER_NAME,
        adapter_version=ADAPTER_VERSION, manifest_uri="cinegraph:missing-original-enwiki-snapshots-v1",
        status="running", records_requested=len(selected), started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    headers = {
        "User-Agent": get_settings().wikidata_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }
    try:
        with httpx.Client(timeout=60, headers=headers) as client:
            for index, (old, item) in enumerate(selected):
                payload = fetch_pinned_revision(client, old.source_revision, item.external_id)
                stored, created = snapshot(
                    db, item=item, run=run, payload=payload,
                    source_revision=old.source_revision, canonical_url=old.canonical_url,
                    license=old.license, attribution_url=old.attribution_url,
                    media_type="application/json", parser_version=ADAPTER_VERSION,
                )
                if not created or verify_snapshot_file(stored.storage_uri, stored.content_hash, stored.byte_size) != "verified":
                    raise RevisionRecoveryError(f"New snapshot for {item.external_id} failed verification.")
                run.records_snapshotted += 1
                db.commit()
                result["fetched"] = run.records_snapshotted
                if run.records_snapshotted % 25 == 0:
                    print(f"recovered={run.records_snapshotted}/{len(selected)}", flush=True)
                if index + 1 < len(selected):
                    time.sleep(max(get_settings().source_request_interval_seconds, 1.0))
        run.status = "complete"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        result["status"] = "complete"
    except (httpx.HTTPError, RevisionRecoveryError) as error:
        db.rollback()
        run.status = "failed"
        run.error_summary = str(error)[:1000]
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        result["status"] = "failed"
        result["error"] = str(error)
    return result


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Paced, resumable recovery of pinned English Wikipedia revisions.")
    parser.add_argument("--limit", type=int, help="Maximum number of original snapshots to reacquire.")
    parser.add_argument("--execute", action="store_true", help="Actually make API requests and store new immutable snapshots.")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    with SessionLocal() as db:
        result = recover(db, limit=args.limit, execute=args.execute)
    print(json.dumps(result, indent=2))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
