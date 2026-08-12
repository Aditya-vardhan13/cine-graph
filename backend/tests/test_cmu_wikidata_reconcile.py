from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CorpusRecord, Film
from app.services.cmu_movie_summaries import source_for_cmu
from app.services.cmu_wikidata_reconcile import reconcile_cmu_records


def test_reconciles_only_an_exact_freebase_identifier_match() -> None:
    engine = create_engine("sqlite://")
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
    engine = create_engine("sqlite://")
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
