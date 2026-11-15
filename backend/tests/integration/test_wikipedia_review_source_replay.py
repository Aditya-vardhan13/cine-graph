"""Explicit local canary: replay real retained HTML into an isolated database."""
import hashlib
import gzip
import json
import os
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (CanonicalEntity, DataSource, Film, LanguageEdition, NarrativePassage,
                        NarrativeUseDecision, RawIngestionRun, SourceAssertion, SourceObject, SourceSnapshot)
from app.services.current_narrative_passages import current_passage_rows
from scripts.replay_wikipedia_review_source import equivalent_recovered_prior, replay
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_missing_current_can_use_only_exact_verified_recovered_projection(tmp_path):
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    payload = b"retained source bytes"
    raw = tmp_path / "retained.json"
    raw.write_bytes(payload)
    with Session(engine) as db:
        source = DataSource(name="English Wikipedia", url="https://en.wikipedia.org/", source_type="revisioned_narrative_context",
                            license="CC BY-SA 4.0", rights_status="attributed_reuse")
        entity = CanonicalEntity(canonical_label="Example", entity_kind="film", wikidata_id="Q1")
        db.add_all([source, entity])
        db.flush()
        obj = SourceObject(source_id=source.id, external_id="enwiki:1", object_kind="wiki_page",
                           canonical_url="https://en.wikipedia.org/wiki/Example")
        db.add(obj)
        db.flush()
        prior = SourceSnapshot(source_object_id=obj.id, source_revision="10", canonical_url=obj.canonical_url,
                               content_hash=hashlib.sha256(payload).hexdigest(), byte_size=len(payload),
                               storage_uri=raw.as_uri(), license="CC BY-SA 4.0", fetch_status="success")
        current = SourceSnapshot(source_object_id=obj.id, source_revision="10", canonical_url=obj.canonical_url,
                                 content_hash="b" * 64, storage_uri=(tmp_path / "missing.json").as_uri(),
                                 license="CC BY-SA 4.0", fetch_status="success")
        db.add_all([prior, current])
        db.flush()
        for snapshot in (prior, current):
            db.add(NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=snapshot.id,
                                    section_locator="plot", section_title="Plot", ordinal=0, content="A story.",
                                    content_hash=hashlib.sha256(b"A story.").hexdigest(), extraction_version="v1"))
        db.flush()
        assert equivalent_recovered_prior(db, prior, current)
        row = db.scalar(select(NarrativePassage).where(NarrativePassage.source_snapshot_id == current.id))
        row.content = "Tampered."
        db.flush()
        assert not equivalent_recovered_prior(db, prior, current)
        row.content = "A story."
        current.source_revision = "11"
        db.flush()
        assert not equivalent_recovered_prior(db, prior, current)
    engine.dispose()


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_retained_hamilton_replay_preserves_old_snapshot_and_no_approval(tmp_path, encoding):
    if os.environ.get("CINEGRAPH_HAMILTON_REPLAY_TEST") != "1":
        pytest.skip("explicit local retained Hamilton capture only")
    original_path = Path("data/evaluation/writer-source-audit/hamilton-current-v1/manifest.json").resolve()
    manifest = json.loads(original_path.read_bytes())
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", script="Latin", enabled=True, status="active"))
        source = DataSource(name="English Wikipedia", url="https://en.wikipedia.org/",
                            source_type="revisioned_narrative_context", license="CC BY-SA 4.0",
                            rights_status="attributed_reuse")
        entity = CanonicalEntity(canonical_label="Hamilton (2020 film)", entity_kind="film", wikidata_id="Q84323848")
        db.add_all([source, entity])
        db.flush()
        db.add(Film(entity_id=entity.id, canonical_title=entity.canonical_label, wikidata_id=entity.wikidata_id,
                    original_language_code="en"))
        obj = SourceObject(source_id=source.id, external_id="enwiki:63015598", object_kind="wiki_page",
                           canonical_url=manifest["canonical_url"])
        db.add(obj)
        db.flush()
        old = SourceSnapshot(source_object_id=obj.id, source_revision="1367628810",
                             canonical_url=obj.canonical_url, content_hash="a" * 64,
                             storage_uri="file:///historical-retained-elsewhere", license="CC BY-SA 4.0",
                             attribution_url=obj.canonical_url, fetch_status="success")
        db.add(old)
        db.flush()
        db.add(SourceAssertion(source_snapshot_id=old.id, statement_locator="qid", source_property="wikidata_item",
                               raw_subject={}, raw_value={"wikidata_id": entity.wikidata_id}, raw_qualifiers={},
                               extractor_version="fixture"))
        db.commit()
        old_id, entity_id = old.id, entity.id
        payload = (original_path.parent / f"{manifest['sha256']}.html").read_bytes()
        capture_dir = tmp_path / "capture"
        capture_dir.mkdir()
        capture_path = capture_dir / f"{manifest['sha256']}.html"
        if encoding == "gzip":
            capture_path = capture_path.with_suffix(".html.gz")
            capture_path.write_bytes(gzip.compress(payload, mtime=0))
        else:
            capture_path.write_bytes(payload)
        manifest.update({"storage_encoding": encoding, "prior_snapshot_id": str(old_id),
                         "prior_sha256": "a" * 64, "prior_revision": "1367628810"})
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_path = capture_dir / "manifest.json"
        manifest_path.write_bytes(manifest_bytes)
        wrong_prior = {**manifest, "prior_sha256": "b" * 64}
        wrong_bytes = json.dumps(wrong_prior, sort_keys=True).encode()
        wrong_path = capture_dir / "wrong.json"
        wrong_path.write_bytes(wrong_bytes)
        with pytest.raises(ValueError, match="does not match the pinned prior snapshot"):
            replay(db, manifest_path=wrong_path, expected_manifest_sha256=hashlib.sha256(wrong_bytes).hexdigest(),
                   storage_root=tmp_path)
        db.rollback()
        with pytest.raises(ValueError, match="manifest hash mismatch"):
            replay(db, manifest_path=manifest_path, expected_manifest_sha256="0" * 64, storage_root=tmp_path)
        report = replay(db, manifest_path=manifest_path, expected_manifest_sha256=manifest_hash, storage_root=tmp_path)
        assert report["created"] and report["source_revision"] == str(manifest["metadata"]["revision_id"])
        assert report["passages_created"] > 9
        current = current_passage_rows(db, {entity_id})
        synopsis = [passage for passage, _ in current if passage.section_locator.startswith("synopsis")]
        assert len(synopsis) == 9
        assert all(str(snapshot.id) == report["snapshot_id"] for _, snapshot in current)
        assert db.get(SourceSnapshot, old_id).source_revision == "1367628810"
        assert db.scalar(select(func.count()).select_from(NarrativeUseDecision)) == 0
        assert db.scalar(select(func.count()).select_from(NarrativePassage)) == report["passages_created"]
        run = db.scalar(select(RawIngestionRun).where(RawIngestionRun.manifest_hash == manifest_hash))
        retained_manifest = Path(unquote(urlsplit(run.manifest_uri).path))
        assert hashlib.sha256(retained_manifest.read_bytes()).hexdigest() == manifest_hash
        repeated = replay(db, manifest_path=manifest_path, expected_manifest_sha256=manifest_hash, storage_root=tmp_path)
        assert repeated["created"] is False and repeated["passages_created"] == 0
        assert db.scalar(select(func.count()).select_from(SourceSnapshot)) == 2
        db.add(NarrativeUseDecision(source_snapshot_id=UUID(report["snapshot_id"]),
                                    use_case="semantic_index_and_model_input", decision="approved",
                                    decision_version=1, reviewer="test-only", decision_notes="Isolated fixture.",
                                    decision_basis_url="https://creativecommons.org/licenses/by-sa/4.0/"))
        db.commit()
        with pytest.raises(ValueError, match="Previously approved source"):
            replay(db, manifest_path=manifest_path, expected_manifest_sha256=manifest_hash, storage_root=tmp_path)
        db.rollback()
    engine.dispose()
