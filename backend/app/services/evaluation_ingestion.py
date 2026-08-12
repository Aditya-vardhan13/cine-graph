"""Run the raw-source foundation pipeline for a selected title/year manifest."""
from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RawIngestionRun, RawIngestionRunSnapshot, SourceAssertion
from app.services.wikidata_raw import ingest_selected_qids
from app.services.wikidata_selection_resolution import resolve_entries
from app.services.wikipedia_raw import ingest_title_year_entries, read_manifest


def qids_from_wikipedia_run(db: Session, manifest_uri: str) -> list[str]:
    run = db.scalar(select(RawIngestionRun).where(
        RawIngestionRun.adapter_name == "wikipedia_api_revision_snapshot",
        RawIngestionRun.manifest_uri == manifest_uri,
    ).order_by(RawIngestionRun.created_at.desc()))
    if not run:
        return []
    rows = db.scalars(select(SourceAssertion).join(
        RawIngestionRunSnapshot, RawIngestionRunSnapshot.source_snapshot_id == SourceAssertion.source_snapshot_id,
    ).where(
        RawIngestionRunSnapshot.ingestion_run_id == run.id,
        SourceAssertion.source_property == "wikidata_item",
    )).all()
    return sorted({str(row.raw_value.get("wikidata_id")) for row in rows if row.raw_value.get("wikidata_id")})


def ingest_manifest(db: Session, manifest: Path, limit: int | None = None) -> dict[str, object]:
    entries, manifest_hash = read_manifest(manifest, limit=limit)
    manifest_uri = manifest.resolve().as_uri()
    resolved, unresolved = resolve_entries(entries)
    qids = [str(entry["wikidata_id"]) for entry in resolved]
    wikidata = ingest_selected_qids(db, qids, manifest_uri=manifest_uri) if qids else {"objects": 0, "snapshots": 0, "source_assertions": 0}
    wikipedia = ingest_title_year_entries(db, resolved, manifest_uri=manifest_uri)
    return {
        "manifest_sha256": manifest_hash,
        "entries": len(entries), "resolved_selection": len(resolved), "unresolved_selection": unresolved,
        "wikidata_qids": len(qids),
        "wikipedia": wikipedia,
        "wikidata": wikidata,
    }


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Run Wikipedia then Wikidata raw snapshot collection for a private title/year manifest.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run_migrations()
    with SessionLocal() as db:
        print(ingest_manifest(db, args.manifest, limit=args.limit))


if __name__ == "__main__":
    main()
