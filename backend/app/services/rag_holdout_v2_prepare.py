"""Append source-preserving parser holdout canaries in cinegraph_eval only.

No retrieval, ranking, label migration, working-corpus mutation, or crawling.
Retained snapshot files must be mounted read-only at their recorded paths.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from app.models import CanonicalEntity, EvidenceChunk, EvidenceChunkRun, ReferenceCollection, ReferenceCollectionMembership, SourceSnapshot
from app.services.wikipedia_research import _snapshot_payload, snapshot_wikitext
from app.services.wikipedia_passages_v2 import materialise_passages
from app.services.wikipedia_text_v2 import EXTRACTION_VERSION as V2_VERSION
from app.services.wikipedia_text_v3 import EXTRACTION_VERSION as V3_VERSION, derive_passages as derive_v3

COLLECTIONS = {"v2": "english-holdout-8-parser-canary-v2",
               "v3": "english-holdout-8-parser-canary-v3"}


def validate_manifest(manifest: dict) -> list[str]:
    pairs = manifest.get("pairs", [])
    qids = [qid for pair in pairs for qid in pair.get("films", [])]
    if (len(pairs) != 4 or len({pair.get("id") for pair in pairs}) != 4
            or any(len(pair.get("films", [])) != 2 or len(pair.get("questions", [])) != 5 for pair in pairs)
            or len(qids) != 8 or len(set(qids)) != 8
            or any(not isinstance(qid, str) or not re.fullmatch(r"Q[1-9][0-9]*", qid) for qid in qids)
            or not manifest.get("version")):
        raise ValueError("A versioned holdout of four disjoint film pairs is required.")
    return qids


def prepare(db: Session, manifest: dict, *, source_run_id: UUID, extraction: str = "v2") -> dict:
    if db.bind is None or db.bind.url.database != "cinegraph_eval":
        raise ValueError("Holdout derivatives can only be written to cinegraph_eval.")
    qids = validate_manifest(manifest)
    if extraction not in COLLECTIONS:
        raise ValueError("Select an explicitly versioned holdout parser.")
    collection_code = COLLECTIONS[extraction]
    extraction_version = V3_VERSION if extraction == "v3" else V2_VERSION
    run = db.get(EvidenceChunkRun, source_run_id)
    if run is None or run.status != "complete" or run.collection_code != manifest.get("collection"):
        raise ValueError("The explicit source chunk run must be complete and match the frozen collection.")
    rows = db.execute(select(CanonicalEntity.wikidata_id, CanonicalEntity.id, SourceSnapshot)
        .join(EvidenceChunk, EvidenceChunk.subject_entity_id == CanonicalEntity.id)
        .join(SourceSnapshot, SourceSnapshot.id == EvidenceChunk.source_snapshot_id)
        .where(CanonicalEntity.wikidata_id.in_(qids), EvidenceChunk.preprocessing_run_id == source_run_id,
               SourceSnapshot.fetch_status == "success").distinct()).all()
    by_qid = {}
    for qid, entity_id, snapshot in rows:
        if qid in by_qid and by_qid[qid][1].id != snapshot.id:
            raise ValueError(f"Ambiguous source snapshot for {qid}.")
        by_qid[qid] = (entity_id, snapshot)
    if set(by_qid) != set(qids):
        raise ValueError("Every holdout film needs one retained source snapshot in the selected run.")
    # Verify every retained file before writing the first derivative.
    originals = {}
    for qid in qids:
        entity_id, snapshot = by_qid[qid]
        if snapshot.license != "CC BY-SA 4.0" or not snapshot.attribution_url:
            raise ValueError("Every source must have an attributable reusable license.")
        text, _title, _version = snapshot_wikitext(_snapshot_payload(snapshot))
        originals[qid] = (entity_id, snapshot, text)
    selection_version = f"{manifest['version']}:{source_run_id}"
    collection = db.get(ReferenceCollection, collection_code)
    if collection is None:
        db.add(ReferenceCollection(code=collection_code, title=f"English holdout parser-{extraction} canary",
            description="Eval-only source-preserving holdout extraction; never a live catalog.", language_code="en",
            selection_method="frozen-holdout-identity-manifest", selection_version=selection_version))
        db.flush()
    elif collection.selection_version != selection_version:
        raise ValueError("Existing holdout collection has a different frozen identity or source run.")
    members = set(db.scalars(select(ReferenceCollectionMembership.entity_id).where(
        ReferenceCollectionMembership.collection_code == collection_code)))
    expected = {by_qid[qid][0] for qid in qids}
    if members and members != expected:
        raise ValueError("Existing holdout membership differs from the frozen set.")
    if not members:
        db.add_all(ReferenceCollectionMembership(collection_code=collection_code, entity_id=by_qid[qid][0],
            selection_position=index, selection_signals={"wikidata_id": qid},
            source_reference="project:backend/tests/fixtures/rag-holdout-identities-v1.json")
            for index, qid in enumerate(qids, 1))
    counts = []
    for qid in qids:
        entity_id, snapshot, text = originals[qid]
        options = ({"extraction_version": extraction_version, "passage_builder": derive_v3}
                   if extraction == "v3" else {})
        counts.append({"qid": qid, "snapshot_id": str(snapshot.id),
                       **materialise_passages(db, entity_id=entity_id, snapshot=snapshot, wikitext=text, **options)})
    db.commit()
    from app.services.evidence_preprocessing import ChunkConfiguration, build_evidence_chunks
    chunks = build_evidence_chunks(db, collection_code=collection_code,
                                   config=ChunkConfiguration(extraction_version=extraction_version))
    return {"collection": collection_code, "source_run_id": str(source_run_id),
            "extraction_version": extraction_version, "films": counts, "chunk_run": chunks,
            "caution": "New source-derived evidence only; old labels must be re-reviewed, not silently migrated."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--source-run", type=UUID, required=True)
    parser.add_argument("--write-eval", action="store_true")
    parser.add_argument("--extraction", choices=("v2", "v3"), default="v2")
    args = parser.parse_args()
    if make_url(args.database_url).database != "cinegraph_eval" or not args.write_eval:
        raise ValueError("Explicit --write-eval and the isolated cinegraph_eval database are required.")
    manifest = json.loads(args.manifest.read_text())
    engine = create_engine(args.database_url)
    try:
        with Session(engine) as db:
            result = prepare(db, manifest, source_run_id=args.source_run, extraction=args.extraction)
    finally:
        engine.dispose()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
