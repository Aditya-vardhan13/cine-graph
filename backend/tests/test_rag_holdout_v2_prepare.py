import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.services.rag_holdout_manifest import build_manifest
from app.services.rag_holdout_v2_prepare import prepare, validate_manifest


def test_v2_holdout_requires_exactly_four_distinct_pairs():
    fixtures = Path(__file__).parent / "fixtures"
    design = json.loads((fixtures / "rag-holdout-questions-v1.json").read_text())
    identity = json.loads((fixtures / "rag-holdout-identities-v1.json").read_text())
    manifest = build_manifest(design, identity, collection="source")
    assert len(validate_manifest(manifest)) == 8
    manifest["pairs"][1]["films"][0] = manifest["pairs"][0]["films"][0]
    with pytest.raises(ValueError, match="disjoint"):
        validate_manifest(manifest)


def test_v2_preparation_rejects_non_eval_database_before_connecting():
    engine = create_engine("postgresql+psycopg://postgres:postgres@127.0.0.1:5433/cinegraph_test")
    with Session(engine) as db, pytest.raises(ValueError, match="only be written to cinegraph_eval"):
        prepare(db, {}, source_run_id=uuid4())
