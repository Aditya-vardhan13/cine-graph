"""Reconstruct and verify local experimental vector inputs without re-embedding.

This does not import an index, review rights, or alter the working corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from app.services.corpus_build_manifest import canonical_digest
from app.services.embedding_artifacts import document_cache_key
from app.services.evidence_preprocessing import CHUNKER_VERSION, ChunkConfiguration, chunk_passage
from app.services.snapshot_integrity import verify_snapshot_file


def reconstruct(corpus: dict, descriptors: dict, mapping: dict, *, root: Path) -> dict:
    for item in (corpus, descriptors, mapping):
        if canonical_digest({k: v for k, v in item.items() if k != "fingerprint"}) != item["fingerprint"]:
            raise ValueError("artifact_fingerprint_mismatch")
    if descriptors["corpus_fingerprint"] != corpus["fingerprint"] or mapping["corpus_fingerprint"] != corpus["fingerprint"]:
        raise ValueError("corpus_binding_mismatch")
    if mapping["model"] != "qwen3-embedding:4b" or mapping["dimension"] != 1024 or mapping["dtype"] != "float32":
        raise ValueError("unexpected_model_contract")
    sources = {s["snapshot_id"]: s for s in descriptors["sources"]}
    docs = {d["chunk_id"]: d for d in corpus["documents"]}
    if len(sources) != len(descriptors["sources"]) or len(docs) != len(corpus["documents"]):
        raise ValueError("duplicate_source_or_passage")
    for source in sources.values():
        if verify_snapshot_file(source["storage_uri"], source["content_hash"], source["byte_size"]) != "verified":
            raise ValueError("snapshot_integrity_failed")
    matrix_path = (root / mapping["matrix_path"]).resolve()
    if not matrix_path.is_relative_to((root / "data" / "evaluation").resolve()):
        raise ValueError("matrix_outside_local_evaluation")
    with matrix_path.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != mapping["matrix_sha256"]:
            raise ValueError("matrix_integrity_failed")
    matrix = np.load(matrix_path, mmap_mode="r", allow_pickle=False)
    if matrix.shape != (len(mapping["rows"]), mapping["dimension"]) or matrix.dtype != np.float32:
        raise ValueError("matrix_shape_mismatch")
    if not np.isfinite(matrix).all() or np.any(np.linalg.norm(matrix, axis=1) == 0):
        raise ValueError("invalid_vector")
    prepared = {}
    restored = []
    inputs = []
    for index, row in enumerate(mapping["rows"]):
        if row["row"] != index:
            raise ValueError("row_order_mismatch")
        doc = docs[row["passage_id"]]
        source = sources[row["snapshot_id"]]
        if (doc["entity_id"] != row["entity_id"] or doc["source_snapshot_id"] != row["snapshot_id"]
                or doc["source_sha256"] != row["source_sha256"] or source["content_hash"] != row["source_sha256"]
                or doc["section_locator"] != row["section_locator"]
                or hashlib.sha256(doc["content"].encode("utf-8")).hexdigest() != doc["content_sha256"]):
            raise ValueError("passage_or_source_mismatch")
        if row["passage_id"] not in prepared:
            prepared[row["passage_id"]] = chunk_passage(doc["content"], config=ChunkConfiguration())
        candidates = prepared[row["passage_id"]]
        ordinal = row["chunk_ordinal"]
        if ordinal >= len(candidates) or ordinal < 0:
            raise ValueError("chunk_ordinal_mismatch")
        chunk = candidates[ordinal]
        model_input = f"Film: {doc['film_title']}\nSection: {doc['section_title']}\nEvidence: {chunk.content}"
        if (chunk.content_hash != row["chunk_sha256"]
                or hashlib.sha256(model_input.encode("utf-8")).hexdigest() != row["document_input_sha256"]):
            raise ValueError("chunk_or_model_input_mismatch")
        restored.append({**row, "film_qid": doc["film_qid"], "film_title": doc["film_title"],
                         "section_title": doc["section_title"], "content": chunk.content})
        inputs.append(model_input)
    if len({row["chunk_id"] for row in restored}) != len(restored):
        raise ValueError("duplicate_chunk")
    key = document_cache_key(provider="ollama", model_name=mapping["model"], dimensions=mapping["dimension"],
        chunk_run_id=mapping["preprocessing_run_id"], chunker_version=CHUNKER_VERSION, contents=inputs)
    if key != mapping["cache_key"]:
        raise ValueError("document_cache_key_mismatch")
    result = {"schema": "cinegraph.reconstructed-vector-corpus/v1", "corpus_fingerprint": corpus["fingerprint"],
        "descriptor_fingerprint": descriptors["fingerprint"], "mapping_fingerprint": mapping["fingerprint"],
        "matrix_sha256": mapping["matrix_sha256"], "model": mapping["model"], "model_digest": mapping["model_digest"],
        "dimension": mapping["dimension"], "chunker_version": CHUNKER_VERSION, "rows": restored,
        "caution": "Offline retained-corpus experiment only; not an active index or a current rights decision."}
    result["fingerprint"] = canonical_digest(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("corpus", "descriptors", "mapping", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    area = (root / "data" / "evaluation").resolve()
    if any(not path.resolve().is_relative_to(area) for path in vars(args).values()) or args.output.exists():
        raise ValueError("new_local_evaluation_output_required")
    result = reconstruct(*(json.loads(getattr(args, key).read_text()) for key in ("corpus", "descriptors", "mapping")), root=root)
    with args.output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"rows": len(result["rows"]), "fingerprint": result["fingerprint"]}))


if __name__ == "__main__":
    main()
