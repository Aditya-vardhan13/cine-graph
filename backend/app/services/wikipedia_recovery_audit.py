"""Read-only check that pinned-revision recovery reproduces old passages."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NarrativePassage, SourceSnapshot
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.wikipedia_research import chunk_section, clean_wikitext, snapshot_wikitext, split_sections
from app.services.wikipedia_revision_recovery import ADAPTER_VERSION, OLD_ROOT


def passage_keys(wikitext: str) -> set[tuple[str, int, str]]:
    return {
        (str(section["locator"]), ordinal, hashlib.sha256(clean_wikitext(chunk).encode("utf-8")).hexdigest())
        for section in split_sections(wikitext)
        for ordinal, chunk in enumerate(chunk_section(str(section["content"])))
    }


def recovered_passage_keys(snapshot: SourceSnapshot) -> set[tuple[str, int, str]] | None:
    if verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size) != "verified":
        return None
    path = Path(unquote(urlparse(snapshot.storage_uri).path))
    wikitext, _, _ = snapshot_wikitext(json.loads(path.read_text(encoding="utf-8")))
    return passage_keys(wikitext)


def recovery_matches_original(db: Session, recovered: SourceSnapshot) -> bool:
    originals = db.scalars(select(SourceSnapshot).where(
        SourceSnapshot.source_object_id == recovered.source_object_id,
        SourceSnapshot.source_revision == recovered.source_revision,
        SourceSnapshot.storage_uri.like(f"{OLD_ROOT}%"),
        SourceSnapshot.id.in_(select(NarrativePassage.source_snapshot_id)),
    )).all()
    derived = recovered_passage_keys(recovered)
    if derived is None or not originals:
        return False
    return any(
        set(db.execute(select(
            NarrativePassage.section_locator, NarrativePassage.ordinal, NarrativePassage.content_hash,
        ).where(NarrativePassage.source_snapshot_id == old.id))) == derived
        for old in originals
    )


def audit_recovered_passages(db: Session, *, sample_limit: int = 10) -> dict:
    originals = db.scalars(select(SourceSnapshot).where(
        SourceSnapshot.storage_uri.like(f"{OLD_ROOT}%"),
        SourceSnapshot.id.in_(select(NarrativePassage.source_snapshot_id)),
    )).all()
    report: dict[str, object] = {
        "originals_with_passages": len(originals), "recovered": 0,
        "exact_match": 0, "mismatch": 0, "unavailable": 0,
        "old_passage_keys": 0, "matching_passage_keys": 0, "examples": [],
    }
    for old in originals:
        old_keys = set(db.execute(select(
            NarrativePassage.section_locator, NarrativePassage.ordinal, NarrativePassage.content_hash,
        ).where(
            NarrativePassage.source_snapshot_id == old.id,
        )))
        report["old_passage_keys"] += len(old_keys)
        recovered = db.scalar(select(SourceSnapshot).where(
            SourceSnapshot.source_object_id == old.source_object_id,
            SourceSnapshot.source_revision == old.source_revision,
            SourceSnapshot.parser_version == ADAPTER_VERSION,
        ).order_by(SourceSnapshot.retrieved_at.desc()))
        if not recovered:
            report["unavailable"] += 1
            continue
        derived_keys = recovered_passage_keys(recovered)
        if derived_keys is None:
            report["unavailable"] += 1
            continue
        report["recovered"] += 1
        overlap = len(old_keys & derived_keys)
        report["matching_passage_keys"] += overlap
        if old_keys == derived_keys:
            report["exact_match"] += 1
        else:
            report["mismatch"] += 1
            if len(report["examples"]) < sample_limit:
                report["examples"].append({
                    "original_snapshot_id": str(old.id),
                    "recovered_snapshot_id": str(recovered.id),
                    "old_passage_keys": len(old_keys),
                    "derived_passage_keys": len(derived_keys),
                    "matching_passage_keys": overlap,
                })
    return report


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Compare all recovered pinned revisions with prior narrative passages.")
    parser.add_argument("--sample-limit", type=int, default=10)
    args = parser.parse_args()
    if args.sample_limit < 0:
        parser.error("--sample-limit must be non-negative")
    with SessionLocal() as db:
        report = audit_recovered_passages(db, sample_limit=args.sample_limit)
    print(json.dumps(report, indent=2))
    if report["mismatch"] or report["unavailable"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
