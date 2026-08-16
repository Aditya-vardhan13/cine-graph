import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CorpusRecord, Film, FilmReleaseEvent
from app.services.cmu_movie_summaries import source_for_cmu
from app.services.cmu_wikidata_reconcile import reconcile_cmu_records
from app.services.wikidata import ingest
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_reconciles_only_an_exact_freebase_identifier_match() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = source_for_cmu(db)
        db.add(CorpusRecord(
            source_id=source.id,
            external_id="123",
            title="Fixture Film",
            language_codes=["English Language"],
            country_codes=[],
            genres=[],
            raw_metadata={"freebase_movie_id": "/m/fixture"},
        ))
        db.commit()

        stats = reconcile_cmu_records(
            db,
            mapper=lambda _ids: {"/m/fixture": {"Q42"}},
            metadata_fetcher=lambda _ids: [{
                "film": {"value": "http://www.wikidata.org/entity/Q42"},
                "filmLabel": {"value": "Fixture Film"},
                "runtime": {"value": "90"},
            }],
        )

        record = db.scalar(select(CorpusRecord).where(CorpusRecord.external_id == "123"))
        film = db.scalar(select(Film).where(Film.wikidata_id == "Q42"))
        assert stats == {"seen": 1, "matched": 1, "unmatched": 0, "ambiguous": 0, "canonical_films": 1}
        assert record is not None and film is not None
        assert record.film_id == film.id
        assert record.match_method == "wikidata_p646_exact"
        assert record.match_confidence == 1.0


def test_marks_ambiguous_freebase_mappings_for_review() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = source_for_cmu(db)
        db.add(CorpusRecord(
            source_id=source.id,
            external_id="124",
            title="Ambiguous Fixture",
            language_codes=["English Language"],
            country_codes=[],
            genres=[],
            raw_metadata={"freebase_movie_id": "/m/ambiguous"},
        ))
        db.commit()

        stats = reconcile_cmu_records(
            db,
            mapper=lambda _ids: {"/m/ambiguous": {"Q42", "Q43"}},
            metadata_fetcher=lambda _ids: [],
        )

        record = db.scalar(select(CorpusRecord).where(CorpusRecord.external_id == "124"))
        assert stats == {"seen": 1, "matched": 0, "unmatched": 0, "ambiguous": 1, "canonical_films": 0}
        assert record is not None
        assert record.film_id is None
        assert record.match_status == "review_required"


def test_merges_release_places_for_the_same_source_date() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        base = {
            "film": {"value": "http://www.wikidata.org/entity/Q99"},
            "filmLabel": {"value": "Release Fixture"},
            "runtime": {"value": "90"},
            "releaseDate": {"value": "2000-01-01T00:00:00Z"},
        }
        ingest(db, rows=[
            {**base, "releasePlace": {"value": "http://www.wikidata.org/entity/Q30"}},
            {**base, "releasePlace": {"value": "http://www.wikidata.org/entity/Q145"}},
        ])

        events = list(db.scalars(select(FilmReleaseEvent)))
        assert len(events) == 1
        assert events[0].location_ids == ["Q145", "Q30"]
