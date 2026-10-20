"""Current narrative reads must not count superseded source revisions."""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CanonicalEntity, DataSource, NarrativePassage, SourceObject, SourceSnapshot
from app.services.current_narrative_passages import current_passage_rows
from app.services.movie_intake_worker import has_plot
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_current_passages_exclude_old_revision_and_keep_other_source() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        entity = CanonicalEntity(entity_kind="film", canonical_label="Fixture film")
        source = DataSource(name="Fixture", url="https://fixture.test", source_type="narrative",
                            license="CC BY-SA 4.0", rights_status="open")
        db.add_all([entity, source])
        db.flush()
        wiki = SourceObject(source_id=source.id, external_id="wiki-film", object_kind="article",
                            canonical_url="https://fixture.test/wiki-film")
        overview = SourceObject(source_id=source.id, external_id="overview-film", object_kind="overview",
                                canonical_url="https://fixture.test/overview-film")
        db.add_all([wiki, overview])
        db.flush()
        old = SourceSnapshot(source_object_id=wiki.id, source_revision="1", content_hash="a" * 64,
                             canonical_url=wiki.canonical_url, license="CC BY-SA 4.0",
                             retrieved_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        new = SourceSnapshot(source_object_id=wiki.id, source_revision="2", content_hash="b" * 64,
                             canonical_url=wiki.canonical_url, license="CC BY-SA 4.0",
                             retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        other = SourceSnapshot(source_object_id=overview.id, source_revision="1", content_hash="c" * 64,
                               canonical_url=overview.canonical_url, license="CC BY-SA 4.0",
                               retrieved_at=datetime(2025, 6, 1, tzinfo=timezone.utc))
        db.add_all([old, new, other])
        db.flush()
        db.add_all([
            NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=old.id,
                             section_locator="plot", section_title="Plot", content="Former plot",
                             content_hash="d" * 64, extraction_version="fixture"),
            NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=new.id,
                             section_locator="lead", section_title="Lead", content="Current lead",
                             content_hash="e" * 64, extraction_version="fixture"),
            NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=other.id,
                             section_locator="tmdb.overview", section_title="Overview", content="Short overview",
                             content_hash="f" * 64, extraction_version="fixture"),
        ])
        db.flush()

        rows = current_passage_rows(db, {entity.id})
        assert {passage.content for passage, _ in rows} == {"Current lead", "Short overview"}
        assert has_plot(db, entity.id) is False
        newer_without_passages = SourceSnapshot(
            source_object_id=wiki.id, source_revision="3", content_hash="0" * 64,
            canonical_url=wiki.canonical_url, license="CC BY-SA 4.0",
            retrieved_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        db.add(newer_without_passages)
        db.flush()
        assert [passage.content for passage, _ in current_passage_rows(db, {entity.id})] == ["Short overview"]
    engine.dispose()
