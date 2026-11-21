"""Read-only, append-only source inventory; never approves or indexes evidence."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from sqlalchemy import select, text
from app.db import SessionLocal
from app.models import Film, ReferenceCollectionMembership
from app.services.corpus_build_manifest import finalize_manifest, manifest_source
from app.services.current_narrative_passages import current_passage_rows
from app.services.narrative_use_decisions import latest_decisions
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.source_rights_policy import can_use_narrative_semantically


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", default="english-1000-retained-narrative-v1")
    parser.add_argument("--output", required=True)
    parser.add_argument("--path-map", action="append", default=[])
    args = parser.parse_args()
    maps = []
    for spec in args.path_map:
        source, separator, target = spec.partition("=")
        if not separator or any(not Path(root).is_absolute() or Path(root).resolve() == Path("/")
                                for root in (source, target)):
            parser.error("path maps require non-root absolute SOURCE=TARGET")
        maps.append((Path(source), Path(target)))
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        films = list(db.scalars(select(Film).join(
            ReferenceCollectionMembership, ReferenceCollectionMembership.entity_id == Film.entity_id,
        ).where(ReferenceCollectionMembership.collection_code == args.collection,
                ReferenceCollectionMembership.status == "included").order_by(Film.entity_id)))
        if not films:
            raise ValueError("collection_has_no_film_profiles")
        rows = []
        for offset in range(0, len(films), 50):
            rows.extend(current_passage_rows(db, {f.entity_id for f in films[offset:offset + 50]}))
        snapshots = {s.id: s for _, s in rows}
        decisions = latest_decisions(db, set(snapshots))
        integrity = {sid: verify_snapshot_file(s.storage_uri, s.content_hash, s.byte_size,
                     root_mappings=tuple(maps) if args.path_map else None)
                     for sid, s in snapshots.items()}
        grouped = defaultdict(lambda: defaultdict(list))
        for p, s in rows:
            grouped[p.subject_entity_id][s.id].append({
                "id": str(p.id), "section": p.section_locator, "ordinal": p.ordinal,
                "sha256": p.content_hash, "characters": len(p.content),
                "extraction_version": p.extraction_version,
                "hash_verified": hashlib.sha256(p.content.encode()).hexdigest() == p.content_hash,
            })
        output_films = []
        for film in films:
            sources = []
            for sid, passages in sorted(grouped[film.entity_id].items(), key=lambda row: str(row[0])):
                s, d = snapshots[sid], decisions.get(sid)
                approved = can_use_narrative_semantically(
                    decision=d.decision if d else None, basis_url=d.decision_basis_url if d else None,
                    notes=d.decision_notes if d else None, license_name=s.license,
                    attribution_url=s.attribution_url)
                source = manifest_source(snapshot_id=str(sid), snapshot_hash=s.content_hash,
                    source_url=s.canonical_url, revision=s.source_revision,
                    fetch_status=s.fetch_status, integrity=integrity[sid],
                    semantic_approved=approved, passages=passages)
                source.update({"license": s.license, "attribution_url": s.attribution_url,
                               "decision_version": d.decision_version if d else None})
                sources.append(source)
            output_films.append({"entity_id": str(film.entity_id), "title": film.canonical_title,
                "wikidata_id": film.wikidata_id, "sources": sources,
                "build_eligible": any(s["build_eligible"] for s in sources)})
        result = finalize_manifest(args.collection, output_films)
    with Path(args.output).open("x", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({"films": len(output_films),
        "build_eligible_films": sum(f["build_eligible"] for f in output_films),
        "manifest_sha256": result["manifest_sha256"]}))


if __name__ == "__main__":
    main()
