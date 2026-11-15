"""Source-bound profile staging using a retained Wikidata response and PostgreSQL."""
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (Assertion, AssertionEvidence, CanonicalEntity, DataSource, Film, LanguageEdition,
                        NarrativeUseDecision, SourceAssertion, SourceObject, SourceSnapshot)
from app.services.recover_film_profile import stage_missing_profile
from app.services.wikidata_raw import entity_from_entitydata
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_stage_missing_profile_is_source_bound_and_review_required(tmp_path):
    qid = "Q16248515"
    digest = "4bdfbac36a64371b333b8e1a088270bd886758231d6c0c1dbe9fce9d32fe23e4"
    path = Path(f"data/evaluation/writer-source-audit/recovery-v1/snapshots/{qid}/{digest}.json")
    if not path.exists():
        pytest.skip("explicit retained local source fixture is unavailable")
    payload = path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == digest
    item = entity_from_entitydata(json.loads(payload), qid)
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="hi", display_name="Hindi", script="Devanagari", status="planned"))
        entity = CanonicalEntity(entity_kind="film", canonical_label="Gangs of Wasseypur 2", wikidata_id=qid)
        source = DataSource(name="Wikidata", url="https://www.wikidata.org/", source_type="wiki",
                            license="CC0 1.0", rights_status="open")
        db.add_all([entity, source]); db.flush()
        obj = SourceObject(source_id=source.id, external_id=qid, object_kind="wikibase_item",
                           canonical_url=f"https://www.wikidata.org/wiki/{qid}")
        db.add(obj); db.flush()
        snapshot = SourceSnapshot(source_object_id=obj.id, canonical_url=obj.canonical_url,
                                  source_revision=str(item["lastrevid"]), storage_uri=path.resolve().as_uri(),
                                  content_hash=digest, byte_size=len(payload), license="CC0 1.0", fetch_status="success")
        db.add(snapshot); db.flush()
        title = item["labels"]["en"]["value"]
        for prop, locator, value in (("wikidata:label:en", "labels.en", {"language": "en", "text": title}),
                                     ("P31", "claims.P31[0]", item["claims"]["P31"][0]["mainsnak"]),
                                     ("P364", "claims.P364[0]", item["claims"]["P364"][0]["mainsnak"])):
            db.add(SourceAssertion(source_snapshot_id=snapshot.id, statement_locator=locator, source_property=prop,
                                   raw_subject={"wikidata_id": qid}, raw_value=value, raw_qualifiers={},
                                   extractor_version="retained-fixture"))
        db.commit()
        args = dict(qid=qid, snapshot_id=snapshot.id, snapshot_hash=digest, expected_title=title,
                    expected_language="hi", reviewer="test-reviewer", review_note="Exact source identity reviewed in isolated test.")
        for changed in ({"snapshot_hash": "0" * 64}, {"expected_title": "Different title"}, {"expected_language": "en"}):
            with pytest.raises(ValueError):
                stage_missing_profile(db, **{**args, **changed})
            db.rollback()
        film = stage_missing_profile(db, **args)
        assert film.canonical_title == title and film.original_language_code == "hi"
        assert film.review_status == "review_required" and film.entity_id == entity.id
        assert db.scalar(select(func.count()).select_from(Assertion)) == 3
        assert db.scalar(select(func.count()).select_from(AssertionEvidence)) == 3
        assert all(a.review_status == "review_required" for a in db.scalars(select(Assertion)))
        assert db.scalar(select(func.count()).select_from(NarrativeUseDecision)) == 0
        with pytest.raises(ValueError, match="already exists"):
            stage_missing_profile(db, **args)
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Film)) == 0
    engine.dispose()
