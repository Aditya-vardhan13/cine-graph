"""Build a local, inactive ten-film index from verified retained 4B vectors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from uuid import UUID

from sqlalchemy import text

from app.db import SessionLocal
from app.models import EvidenceChunk, Film, ReferenceCollection, ReferenceCollectionMembership
from app.services.corpus_build_manifest import canonical_digest
from app.services.embedding_cache_rebind import rebind_exact_cache
from app.services.embedding_index import _candidate_run, import_embedding_cache
from app.services.embedding_index_audit import audit_index
from app.services.evidence_preprocessing import CHUNKER_VERSION, ChunkConfiguration, build_evidence_chunks
from app.services.ollama_embeddings import MANIFEST_REVISION_PREFIX, OllamaEmbeddingProfile
from audit_recovery_rebind_inputs import audit


COLLECTION = "recovery-pilot-10-inactive-v1"
DIGEST = "df5bd2e3c74cd8d069d21dc038f1b359fcdc9458fce1c99bd43c9eb1518ff907"


def run(db, root: Path, *, apply: bool, cache_dir: Path | None = None) -> dict:
    area = root / "data" / "evaluation"
    corpus = json.loads((area / "recovery-ten-film-current-v1.json").read_text())
    mapping = json.loads((area / "recovery-ten-film-vector-mapping-v2.json").read_text())
    identity = json.loads((root / "data/reports/recovery-pilot-sitelinks-2026-11-23-v1.json").read_text())
    if (canonical_digest({k: v for k, v in identity.items() if k != "report_sha256"}) != identity["report_sha256"]
            or identity["corpus_fingerprint"] != corpus["fingerprint"] or len(identity["rows"]) != 10
            or not all(row["matches_source_url"] for row in identity["rows"])):
        raise ValueError("pilot_identity_crosscheck_failed")
    pairs = {(UUID(d["entity_id"]), d["film_qid"]) for d in corpus["documents"]}
    if len(pairs) != 10 or {qid for _, qid in pairs} != {row["qid"] for row in identity["rows"]}:
        raise ValueError("pilot_identity_scope_mismatch")
    if shutil.disk_usage(root).free < 6 * 1024**3 + 256 * 1024**2:
        raise RuntimeError("insufficient_disk_reserve")
    if db.get(ReferenceCollection, COLLECTION) is not None:
        raise ValueError("pilot_collection_already_exists_inspect_before_retry")
    if db.query(EvidenceChunk.id).filter(EvidenceChunk.narrative_passage_id.in_(
            [UUID(doc["chunk_id"]) for doc in corpus["documents"]]),
            EvidenceChunk.chunker_version == CHUNKER_VERSION).first() is not None:
        raise ValueError("pilot_chunker_rows_already_exist_inspect_before_retry")
    for entity_id, qid in pairs:
        film = db.query(Film).filter_by(entity_id=entity_id, wikidata_id=qid).one_or_none()
        if film is None:
            raise ValueError("pilot_film_identity_mismatch")
    preflight = audit(db, corpus)
    if not preflight["source_match"]:
        raise ValueError("pilot_sources_changed")
    if not apply:
        return {"mode": "preflight", "collection": COLLECTION, **preflight}
    db.add(ReferenceCollection(code=COLLECTION, title="Recovery ten-film pilot (inactive)",
            description="Local evaluation only; not an active or published catalog.", language_code="en",
            selection_method="retained source-bound development pilot", selection_version="v1", status="inactive"))
    db.flush()
    for entity_id, _ in sorted(pairs, key=lambda pair: str(pair[0])):
        db.add(ReferenceCollectionMembership(collection_code=COLLECTION, entity_id=entity_id,
                source_reference="pilot:" + corpus["fingerprint"], status="included"))
    db.flush()
    chunk_report = build_evidence_chunks(db, collection_code=COLLECTION,
            config=ChunkConfiguration(current_extractions_per_snapshot=True))
    run = _candidate_run(db, collection_code=COLLECTION, chunker_version=CHUNKER_VERSION,
                             run_id=UUID(chunk_report["run_id"]))
    profile = OllamaEmbeddingProfile(model="qwen3-embedding:4b", expected_model_digest=DIGEST)
    matrix = (root / mapping["matrix_path"]).resolve()
    if not matrix.is_relative_to(area):
        raise ValueError("matrix_outside_evaluation_area")
    cache = rebind_exact_cache(db, run=run, mapping=mapping, matrix_path=matrix,
            output_dir=cache_dir or area / "recovery-pilot-inactive-rebound-v1", expected_model_digest=DIGEST)
    index = import_embedding_cache(db, cache_path=cache, collection_code=COLLECTION,
            chunker_version=CHUNKER_VERSION, model_name=profile.model,
            model_revision=MANIFEST_REVISION_PREFIX + DIGEST, dimension=profile.dimensions,
            query_instruction=profile.query_instruction, chunk_run_id=run.id)
    result = audit_index(db, index.id)
    if not result["integrity_pass"] or not audit(db, corpus)["source_match"]:
        raise RuntimeError("inactive_pilot_audit_failed_do_not_activate")
    return {"mode": "inactive_build", "collection": COLLECTION, "chunk_run_id": str(run.id),
                          "index_run_id": str(index.id), "vectors": index.chunks_completed,
                          "integrity_pass": True, "activated": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create only an inactive pilot; never activate it.")
    args = parser.parse_args()
    with SessionLocal() as db:
        if not args.apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        print(json.dumps(run(db, Path.cwd().resolve(), apply=args.apply)))


if __name__ == "__main__":
    main()
