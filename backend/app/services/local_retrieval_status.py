"""Read-only status probe for local embedding and retrieval artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import EmbeddingIndexRun, EmbeddingModel


def main() -> None:
    parser = argparse.ArgumentParser(description="Show local CineGraph embedding/index completion state.")
    parser.add_argument("--evaluation-dir", default="data/evaluation")
    arguments = parser.parse_args()
    with SessionLocal() as db:
        rows = db.execute(
            select(EmbeddingIndexRun, EmbeddingModel)
            .join(EmbeddingModel, EmbeddingModel.id == EmbeddingIndexRun.embedding_model_id)
            .order_by(EmbeddingIndexRun.created_at.desc())
        ).all()
    evaluation_dir = Path(arguments.evaluation_dir)
    progress_files = sorted(evaluation_dir.glob("**/*.progress.json")) + sorted(evaluation_dir.glob("*.progress"))
    payload = {
        "indexes": [{
            "index_run_id": str(run.id),
            "model": model.model_name,
            "model_revision": model.model_revision,
            "status": run.status,
            "chunks_completed": run.chunks_completed,
            "chunks_requested": run.chunks_requested,
            "progress_percent": round(run.chunks_completed / run.chunks_requested * 100, 2) if run.chunks_requested else 0.0,
            "error_summary": run.error_summary,
        } for run, model in rows],
        "unfinished_local_artifacts": [str(path) for path in progress_files],
        "ready": bool(rows) and rows[0][0].status == "complete" and not progress_files,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
