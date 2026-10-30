"""Export a content-bound, model-neutral corpus from cinegraph_eval only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from app.models import CanonicalEntity, EvidenceChunk, EvidenceChunkRun, NarrativePassage, SourceSnapshot


def bind_corpus(*, collection: str, run_id: str, documents: list[dict], cases: list[dict]) -> dict:
    """Bind exact evidence and questions, independent of model or ranking order."""
    ordered = sorted(documents, key=lambda row: row["chunk_id"])
    if not ordered or len({row["chunk_id"] for row in ordered}) != len(ordered):
        raise ValueError("Corpus must contain distinct evidence chunks.")
    films = {row["film_qid"] for row in ordered}
    if not cases or any(len(case["film_qids"]) != 2 or
                        not set(case["film_qids"]).issubset(films) for case in cases):
        raise ValueError("Every question needs evidence for both selected films.")
    payload = {"version": "rag-experiment-corpus-v1", "collection": collection,
               "chunk_run_id": run_id, "documents": ordered, "cases": cases}
    payload["fingerprint"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode()).hexdigest()
    return payload


def export_corpus(db: Session, *, manifest: dict, run_id: UUID, pair_count: int) -> dict:
    pairs = manifest["pairs"]
    if not 1 <= pair_count <= len(pairs):
        raise ValueError("Select a non-empty frozen prefix of film pairs.")
    pairs = pairs[:pair_count]
    run = db.get(EvidenceChunkRun, run_id)
    if run is None or run.status != "complete":
        raise ValueError("An explicit completed chunk run is required.")
    qids = {qid for pair in pairs for qid in pair["films"]}
    cases = [{"case_id": f"{pair['id']}-Q{index}", "film_qids": pair["films"],
              "question": question} for pair in pairs
             for index, question in enumerate(pair["questions"], 1)]
    rows = db.execute(select(EvidenceChunk, NarrativePassage, SourceSnapshot,
                             CanonicalEntity.wikidata_id, CanonicalEntity.canonical_label)
        .join(NarrativePassage, NarrativePassage.id == EvidenceChunk.narrative_passage_id)
        .join(SourceSnapshot, SourceSnapshot.id == EvidenceChunk.source_snapshot_id)
        .join(CanonicalEntity, CanonicalEntity.id == EvidenceChunk.subject_entity_id)
        .where(EvidenceChunk.preprocessing_run_id == run_id,
               EvidenceChunk.quality_status == "eligible", CanonicalEntity.wikidata_id.in_(qids)))
    rows = list(rows)
    for chunk, parent, snapshot, _qid, _title in rows:
        if (parent.source_snapshot_id != snapshot.id or
                parent.subject_entity_id != chunk.subject_entity_id or
                hashlib.sha256(chunk.content.encode()).hexdigest() != chunk.content_hash or
                hashlib.sha256(parent.content.encode()).hexdigest() != parent.content_hash):
            raise ValueError("Evidence content or parent/source lineage failed integrity checks.")
    documents = [{
        "chunk_id": str(chunk.id), "film_qid": qid, "film_title": title,
        "source_snapshot_id": str(snapshot.id), "source_revision": snapshot.source_revision,
        "source_content_hash": snapshot.content_hash,
        "source_url": snapshot.attribution_url or snapshot.canonical_url,
        "license": snapshot.license, "extraction_version": parent.extraction_version,
        "section_locator": chunk.section_locator, "section_title": chunk.section_title,
        "passage_ordinal": parent.ordinal, "chunk_ordinal": chunk.chunk_ordinal,
        "content": chunk.content, "content_hash": chunk.content_hash,
        "parent_passage_id": str(parent.id), "parent_content": parent.content,
        "parent_content_hash": parent.content_hash,
    } for chunk, parent, snapshot, qid, title in rows]
    return bind_corpus(collection=run.collection_code, run_id=str(run_id),
                       documents=documents, cases=cases)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--chunk-run", type=UUID, required=True)
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if make_url(args.database_url).database != "cinegraph_eval":
        raise ValueError("Experiment exports may read only cinegraph_eval.")
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    output = args.output.resolve()
    if not output.is_relative_to(root):
        raise ValueError("Export only under ignored project-local data/evaluation.")
    engine = create_engine(args.database_url)
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            result = export_corpus(db, manifest=json.loads(args.manifest.read_text()),
                                   run_id=args.chunk_run, pair_count=args.pairs)
    finally:
        engine.dispose()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"documents": len(result["documents"]), "cases": len(result["cases"]),
                      "fingerprint": result["fingerprint"]}))


if __name__ == "__main__":
    main()
