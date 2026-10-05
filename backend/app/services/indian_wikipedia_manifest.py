"""Derive bounded enwiki revision jobs from retained Wikidata sitelinks.

No network request occurs here. Missing enwiki pages remain an explicit
coverage gap, not an invented title match or a license to scrape HTML.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DataSource, SourceObject, SourceSnapshot


def _entity_from_snapshot(db: Session, qid: str) -> dict | None:
    source = db.scalar(select(DataSource).where(DataSource.name == "Wikidata"))
    if source is None:
        return None
    item = db.scalar(select(SourceObject).where(
        SourceObject.source_id == source.id, SourceObject.external_id == qid,
    ))
    if item is None:
        return None
    retained = db.scalar(select(SourceSnapshot).where(
        SourceSnapshot.source_object_id == item.id,
        SourceSnapshot.fetch_status == "success",
    ).order_by(SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc()))
    if retained is None:
        return None
    uri = urlparse(retained.storage_uri)
    if uri.scheme != "file" or uri.netloc not in ("", "localhost"):
        raise ValueError("Expected a local retained Wikidata source snapshot")
    return json.loads(Path(unquote(uri.path)).read_text(encoding="utf-8"))


def build_manifests(db: Session, selection: Path, output_dir: Path,
                    *, chunk_size: int = 100) -> dict:
    if not 1 <= chunk_size <= 500:
        raise ValueError("chunk_size must be between 1 and 500")
    entries = [json.loads(line) for line in selection.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    resolved = []
    gaps = []
    for entry in entries:
        qid = entry["wikidata_id"]
        entity = _entity_from_snapshot(db, qid)
        if entity is None:
            gaps.append({"wikidata_id": qid, "reason": "no_retained_wikidata_snapshot"})
            continue
        title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
        if not isinstance(title, str) or not title:
            gaps.append({"wikidata_id": qid, "reason": "no_enwiki_sitelink"})
            continue
        resolved.append({
            "title": entry["title"], "year": entry["year"],
            "wikidata_id": qid, "wikipedia_title": title,
            "verified_wikidata_sitelink": True,
        })
    output_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for start in range(0, len(resolved), chunk_size):
        path = output_dir / f"enwiki_chunk_{start // chunk_size + 1:04d}.json"
        path.write_text(json.dumps({
            "schema": "cinegraph.user-selection-manifest/v1",
            "selection_source": str(selection),
            "entries": resolved[start:start + chunk_size],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        files.append(str(path))
    report = {"selected": len(entries), "with_enwiki_sitelink": len(resolved),
              "without_enwiki_sitelink": len(gaps), "gaps": gaps,
              "revision_job_manifests": files}
    (output_dir / "coverage.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build enwiki jobs from retained Wikidata sitelinks")
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--chunk-size", type=int, default=100)
    args = parser.parse_args()
    with SessionLocal() as db:
        report = build_manifests(db, args.selection, args.output_dir,
                                 chunk_size=args.chunk_size)
    print(json.dumps({key: value for key, value in report.items()
                      if key not in {"gaps", "revision_job_manifests"}}))


if __name__ == "__main__":
    main()
