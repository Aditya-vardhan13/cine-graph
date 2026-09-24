"""Read-only integrity audit for locally retained source snapshots.

The database descriptor is not proof that the captured bytes are still present.
This audit checks the original storage URI and checksum without repairing or
replacing either the snapshot record or its derived assertions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Assertion, AssertionEvidence, DataSource, SourceAssertion, SourceObject, SourceSnapshot


def verify_snapshot_file(storage_uri: str | None, expected_hash: str, expected_size: int | None) -> str:
    """Return a precise status; never trust file presence without its digest."""
    if not storage_uri:
        return "no_uri"
    parsed = urlparse(storage_uri)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return "unsupported_uri"
    path = Path(unquote(parsed.path))
    if not path.is_file():
        return "missing"
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError:
        return "unreadable"
    if digest.hexdigest() != expected_hash:
        return "hash_mismatch"
    if expected_size is not None and size != expected_size:
        return "size_mismatch"
    return "verified"


def audit_snapshots(db: Session, *, source_name: str | None = None, sample_limit: int = 5) -> dict:
    """Inspect current descriptors without writing to the working database."""
    query = (
        select(DataSource.name, SourceSnapshot.id, SourceSnapshot.storage_uri,
               SourceSnapshot.content_hash, SourceSnapshot.byte_size)
        .join(SourceObject, SourceObject.source_id == DataSource.id)
        .join(SourceSnapshot, SourceSnapshot.source_object_id == SourceObject.id)
        .order_by(DataSource.name, SourceSnapshot.id)
    )
    if source_name:
        query = query.where(DataSource.name == source_name)
    counts: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    unavailable_ids = []
    for name, snapshot_id, uri, digest, byte_size in db.execute(query):
        status = verify_snapshot_file(uri, digest, byte_size)
        counts[name][status] += 1
        if status != "verified":
            unavailable_ids.append(snapshot_id)
        if status != "verified" and len(examples[name][status]) < sample_limit:
            examples[name][status].append({"snapshot_id": str(snapshot_id), "storage_uri": uri or ""})
    linked_assertions: dict[str, dict[str, int]] = defaultdict(dict)
    if unavailable_ids:
        impact = db.execute(
            select(DataSource.name, Assertion.review_status, func.count(func.distinct(Assertion.id)))
            .select_from(Assertion)
            .join(AssertionEvidence, AssertionEvidence.assertion_id == Assertion.id)
            .join(SourceAssertion, SourceAssertion.id == AssertionEvidence.source_assertion_id)
            .join(SourceSnapshot, SourceSnapshot.id == SourceAssertion.source_snapshot_id)
            .join(SourceObject, SourceObject.id == SourceSnapshot.source_object_id)
            .join(DataSource, DataSource.id == SourceObject.source_id)
            .where(SourceSnapshot.id.in_(unavailable_ids))
            .group_by(DataSource.name, Assertion.review_status)
        )
        for name, review_status, count in impact:
            linked_assertions[name][review_status] = count
    return {
        "total": sum(sum(source_counts.values()) for source_counts in counts.values()),
        "sources": {
            name: {
                "counts": dict(source_counts), "examples": dict(examples[name]),
                "explicitly_linked_assertions_with_unavailable_source": linked_assertions[name],
            }
            for name, source_counts in sorted(counts.items())
        },
    }


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Read-only audit of local source snapshot bytes and hashes.")
    parser.add_argument("--source", help="Limit the audit to one registered source name.")
    parser.add_argument("--sample-limit", type=int, default=5)
    args = parser.parse_args()
    if args.sample_limit < 0:
        parser.error("--sample-limit must be non-negative")
    with SessionLocal() as db:
        print(json.dumps(audit_snapshots(db, source_name=args.source, sample_limit=args.sample_limit), indent=2))


if __name__ == "__main__":
    main()
