"""Complete the existing inactive pilot, re-embedding only changed input headers.

Explicit local operation: never selects an active index or changes source labels.
Retained matrices and mappings are immutable; output uses a new cache directory.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import numpy as np
from sqlalchemy import select

from app.db import SessionLocal
from app.models import EvidenceChunkRun, ReferenceCollection, SourceSnapshot
from app.services.corpus_build_manifest import canonical_digest
from app.services.embedding_artifacts import document_cache_key
from app.services.embedding_evaluation import _cached_ollama_document_embeddings
from app.services.embedding_index import _ordered_chunks_and_contents, import_embedding_cache
from app.services.embedding_index_audit import audit_index
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile, MANIFEST_REVISION_PREFIX
from audit_recovery_rebind_inputs import audit
from build_inactive_recovery_pilot import COLLECTION, DIGEST


class ReserveCheckedClient(OllamaEmbeddingClient):
    def embed(self, values, *, profile):
        if shutil.disk_usage(Path.cwd()).free < 6 * 1024**3 + 256 * 1024**2:
            raise RuntimeError("disk_reserve")
        result = super().embed(values, profile=profile)
        matrix = np.asarray(result)
        if not np.isfinite(matrix).all() or np.any(np.linalg.norm(matrix,axis=1)==0):
            raise ValueError("invalid_new_vectors")
        return result


def main():
    root = Path.cwd()
    area = root / "data/evaluation"
    output = area / "recovery-pilot-current-header-cache-v1"
    if shutil.disk_usage(root).free < 6 * 1024**3 + 512 * 1024**2:
        raise RuntimeError("disk_reserve")
    corpus = json.loads((area / "recovery-ten-film-current-v1.json").read_text())
    mapping = json.loads((area / "recovery-ten-film-vector-mapping-v2.json").read_text())
    with SessionLocal() as db:
        collection = db.get(ReferenceCollection, COLLECTION)
        if collection is None or collection.status != "inactive":
            raise ValueError("existing_inactive_pilot_required")
        runs = list(db.scalars(select(EvidenceChunkRun).where(EvidenceChunkRun.collection_code == COLLECTION)))
        if len(runs) != 1 or not audit(db, corpus)["source_match"]:
            raise ValueError("pilot_source_or_run_mismatch")
        run = runs[0]
        chunks, contents = _ordered_chunks_and_contents(db, run)
        if canonical_digest({k:v for k,v in mapping.items() if k != "fingerprint"}) != mapping["fingerprint"]:
            raise ValueError("mapping_integrity_failed")
        rows = { (r["passage_id"], r["chunk_ordinal"], r["chunk_sha256"]): r for r in mapping["rows"] }
        if len(rows) != len(chunks):
            raise ValueError("mapping_count_mismatch")
        if (mapping["model_digest"] != DIGEST or mapping["model"] != "qwen3-embedding:4b"
                or mapping["dimension"] != 1024 or mapping["dtype"] != "float32"
                or mapping["corpus_fingerprint"] != corpus["fingerprint"]):
            raise ValueError("mapping_profile_mismatch")
        current_hashes = {(str(c.narrative_passage_id),c.chunk_ordinal,c.content_hash):hashlib.sha256(s.encode()).hexdigest()
                          for c,s in zip(chunks, contents, strict=True)}
        matrix_path = (root / mapping["matrix_path"]).resolve()
        if not matrix_path.is_relative_to(area.resolve()):
            raise ValueError("matrix_outside_evaluation_area")
        with matrix_path.open("rb") as handle:
            if hashlib.file_digest(handle,"sha256").hexdigest() != mapping["matrix_sha256"]:
                raise ValueError("matrix_integrity_failed")
        original = np.load(matrix_path,allow_pickle=False)
        if (original.dtype != np.float32 or original.shape != (len(chunks),1024)
                or not np.isfinite(original).all() or np.any(np.linalg.norm(original,axis=1)==0)):
            raise ValueError("invalid_original_matrix")
        if [r["row"] for r in mapping["rows"]] != list(range(len(chunks))):
            raise ValueError("invalid_row_order")
        vectors = np.empty_like(original)
        for i,c in enumerate(chunks):
            r=rows[(str(c.narrative_passage_id),c.chunk_ordinal,c.content_hash)]
            source=db.get(SourceSnapshot,c.source_snapshot_id)
            if (r["entity_id"] != str(c.subject_entity_id) or r["snapshot_id"] != str(c.source_snapshot_id)
                    or r["section_locator"] != c.section_locator or r["source_sha256"] != source.content_hash
                    or hashlib.sha256(c.content.encode()).hexdigest() != c.content_hash):
                raise ValueError("source_chunk_mismatch")
            vectors[i] = original[r["row"]]
        changed = [i for i,c in enumerate(chunks) if rows[(str(c.narrative_passage_id),c.chunk_ordinal,c.content_hash)]
                   ["document_input_sha256"] != current_hashes[(str(c.narrative_passage_id),c.chunk_ordinal,c.content_hash)]]
        print(json.dumps({"exact_reused":len(chunks)-len(changed),"regenerate":len(changed)}), flush=True)
        profile = OllamaEmbeddingProfile(model="qwen3-embedding:4b", expected_model_digest=DIGEST)
        client = ReserveCheckedClient(base_url="http://host.docker.internal:11434")
        fresh, _ = _cached_ollama_document_embeddings(client, [contents[i] for i in changed],
            profile=profile, run=run, batch_size=1, cache_dir=output / "changed-inputs")
        vectors[changed] = fresh
        key = document_cache_key(provider="ollama",model_name=profile.model,dimensions=1024,
            chunk_run_id=str(run.id),chunker_version=run.chunker_version,contents=contents)
        final = output / f"qwen3-embedding--4b-{key}.npy"
        with final.open("xb") as handle:
            np.save(handle,vectors,allow_pickle=False)
        if not audit(db, corpus)["source_match"]:
            raise ValueError("source_changed_during_generation")
        index = import_embedding_cache(db,cache_path=final,collection_code=COLLECTION,
            chunker_version=run.chunker_version,model_name=profile.model,model_revision=MANIFEST_REVISION_PREFIX+DIGEST,
            query_instruction=profile.query_instruction,chunk_run_id=run.id)
        result = audit_index(db,index.id)
        print(json.dumps(result),flush=True)
        if not result["integrity_pass"]:
            raise RuntimeError("inactive_index_audit_failed")


if __name__ == "__main__":
    main()
