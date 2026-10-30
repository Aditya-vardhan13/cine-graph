"""Resumeable local 0.6B embedding/index job for the ten-film v2 canary only."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from app.services.embedding_evaluation import _cached_ollama_document_embeddings, _document_cache_key
from app.services.embedding_index import _candidate_run, _ordered_chunks_and_contents, import_embedding_cache, index_status
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.wikipedia_passages_v2 import CANARY_COLLECTION


MODEL_REVISION = "sha256:06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439"
CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "evaluation" / "parser-v2-embedding-cache"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--write-eval", action="store_true")
    args = parser.parse_args()
    if make_url(args.database_url).database != "cinegraph_eval" or not args.write_eval:
        raise ValueError("The canary index requires explicit --write-eval and cinegraph_eval.")
    if not 1 <= args.batch_size <= 24:
        raise ValueError("The local embedding batch must be between 1 and 24.")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(CACHE_DIR).free < 2 * 1024**3:
        raise RuntimeError("Keep at least 2 GiB free before the local embedding canary.")
    engine = create_engine(args.database_url, pool_pre_ping=True)
    profile = OllamaEmbeddingProfile()
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            run = _candidate_run(db, collection_code=CANARY_COLLECTION, chunker_version="spacy-sentencizer-evidence-v4")
            chunks, contents = _ordered_chunks_and_contents(db, run)
            if not chunks or len({chunk.subject_entity_id for chunk in chunks}) != 10:
                raise ValueError("The parser-v2 canary must contain eligible chunks for exactly ten films.")
            key = _document_cache_key(profile=profile, run=run, contents=contents)
            cache_path = CACHE_DIR / f"{profile.model.replace('/', '--').replace(':', '--')}-{key}.npy"
        client = OllamaEmbeddingClient(base_url=args.ollama_url)
        matrix, reused = _cached_ollama_document_embeddings(
            client, contents, profile=profile, run=run,
            batch_size=args.batch_size, cache_dir=CACHE_DIR,
        )
        if matrix.shape != (len(chunks), profile.dimensions):
            raise RuntimeError("Canary vector cache shape does not match the pinned chunks.")
        del matrix
        with Session(engine) as db:
            index = import_embedding_cache(
                db, cache_path=cache_path, collection_code=CANARY_COLLECTION,
                chunker_version=run.chunker_version, model_name=profile.model,
                model_revision=MODEL_REVISION, dimension=profile.dimensions,
                query_instruction=profile.query_instruction,
            )
            report = {"document_cache_reused": reused, "eligible_chunks": len(chunks), **index_status(db, str(index.id))}
    finally:
        engine.dispose()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
