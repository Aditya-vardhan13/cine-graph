"""Replay a real retained recovery capture into an isolated PostgreSQL schema."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Assertion, DataSource, Film, SourceAssertion, SourceObject, SourceSnapshot
from app.services.wikidata_raw import entity_from_entitydata
from scripts.audit_writer_identity_recovery import audit_recovery
from scripts.audit_writer_replay_preflight import preflight
from scripts.replay_writer_identity_sources import replay
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_new_capture_is_source_only_idempotent_and_preserves_missing_old_snapshot(tmp_path):
    if os.environ.get("CINEGRAPH_RECOVERY_SOURCE_TEST") != "1":
        pytest.skip("explicit retained-source recovery replay only")
    root = Path("data/evaluation/writer-source-audit/recovery-v1").resolve()
    checkpoint = json.loads((root / "checkpoint.json").read_bytes())
    qid = "Q175038"
    record = checkpoint["captures"][qid]
    payload = (root / record["snapshot_path"]).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == record["sha256"]
    entity = entity_from_entitydata(json.loads(payload), qid)
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = DataSource(name="Wikidata", url="https://www.wikidata.org/", source_type="structured_metadata",
                            license="CC0 1.0", rights_status="open")
        db.add(source)
        db.flush()
        obj = SourceObject(source_id=source.id, external_id=qid, object_kind="wikibase_item",
                           canonical_url=f"https://www.wikidata.org/wiki/{qid}")
        db.add(obj)
        db.flush()
        old_uri = "file:///missing-historical-fixture.json"
        old = SourceSnapshot(source_object_id=obj.id, source_revision=str(record["previous_revision"]),
                             canonical_url=obj.canonical_url, content_hash=record["previous_sha256"],
                             storage_uri=old_uri, license="CC0 1.0", fetch_status="success")
        db.add(old)
        db.commit()
        old_id = old.id
        # Build a local one-item review packet from the real capture. This is a
        # test-only manifest; it grants no identity or rights approval.
        audit_data = {"schema": "cinegraph.writer-source-identity-audit/v1", "review_status": "review_required",
                      "entries": [{"wikidata_id": qid, "film_title": "12 Monkeys",
                                   "issues": ["wikidata_snapshot_unavailable"],
                                   "wikipedia_url": "https://en.wikipedia.org/wiki/12_Monkeys",
                                   "wikidata_snapshot_id": str(old_id),
                                   "wikidata_revision": record["previous_revision"],
                                   "wikidata_sha256": record["previous_sha256"]}]}
        audit_path = tmp_path / "audit.json"
        audit_path.write_text(json.dumps(audit_data), encoding="utf-8")
        recovery = tmp_path / "recovery"
        recovery.mkdir()
        (recovery / "capture.json").write_bytes(payload)
        record = dict(record, previous_snapshot_id=str(old_id), snapshot_path="capture.json")
        (recovery / "checkpoint.json").write_text(json.dumps({
            "schema": "cinegraph.writer-identity-recovery/v1",
            "audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
            "captures": {qid: record},
        }), encoding="utf-8")
        recovery_audit = tmp_path / "recovery-audit.json"
        recovery_audit.write_text(json.dumps(audit_recovery(audit_path, recovery)), encoding="utf-8")
        ready = preflight(db, audit_path, recovery, recovery_audit)
        assert ready["counts"]["ready_for_source_retention"] == 1
        old.source_revision = "wrong-revision"
        db.flush()
        mismatch = preflight(db, audit_path, recovery, recovery_audit)
        assert mismatch["counts"]["prior_snapshot_descriptor_changed"] == 1
        db.rollback()
        result = replay(db, plan=ready, plan_hash="c" * 64, audit_path=audit_path,
                        recovery_dir=recovery, recovery_audit_path=recovery_audit,
                        snapshot_root=tmp_path / "raw", disk_check_path=tmp_path, limit=1)
        assert result["counts"]["new_snapshots"] == 1 and result["counts"]["source_assertions"] > 0
        repeated = replay(db, plan=ready, plan_hash="c" * 64, audit_path=audit_path,
                          recovery_dir=recovery, recovery_audit_path=recovery_audit,
                          snapshot_root=tmp_path / "raw", disk_check_path=tmp_path, limit=1)
        assert repeated["counts"].get("new_snapshots", 0) == 0
        assert repeated["counts"]["already_retained"] == 1
        assert db.scalar(select(func.count()).select_from(SourceSnapshot)) == 2
        assert db.scalar(select(func.count()).select_from(SourceAssertion)) > 0
        assert db.scalar(select(func.count()).select_from(Assertion)) == 0
        assert db.scalar(select(func.count()).select_from(Film)) == 0
        original = db.get(SourceSnapshot, old_id)
        assert original.storage_uri == old_uri and original.content_hash == record["previous_sha256"]
    engine.dispose()
