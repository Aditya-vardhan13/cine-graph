from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CanonicalEntity, ReferenceCollectionMembership
from app.services.english_reference_shelf import Candidate, COLLECTION_CODE, fetch_reference_candidates, ingest_reference_shelf


def _row(qid: str, title: str, release: str) -> dict:
    return {
        "film": {"value": f"http://www.wikidata.org/entity/{qid}"},
        "filmLabel": {"value": title},
        "releaseDate": {"value": release},
    }


def test_reference_shelf_is_idempotent_and_retains_selection_signals() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    candidates = [Candidate("Q1", 200), Candidate("Q2", 150)]
    rows = [_row("Q1", "First fixture", "2014-01-01T00:00:00Z"), _row("Q2", "Second fixture", "2020-01-01T00:00:00Z")]
    with Session(engine) as db:
        first = ingest_reference_shelf(db, candidates=candidates, rows=rows)
        second = ingest_reference_shelf(db, candidates=candidates, rows=rows)
        memberships = list(db.scalars(select(ReferenceCollectionMembership).where(
            ReferenceCollectionMembership.collection_code == COLLECTION_CODE
        )))
        entities = list(db.scalars(select(CanonicalEntity).where(CanonicalEntity.wikidata_id.in_(("Q1", "Q2")))))

        assert first["memberships_created"] == 2
        assert second["memberships_created"] == 0
        assert [(item.selection_position, item.selection_signals["wikidata_sitelink_count"]) for item in memberships] == [(1, 200), (2, 150)]
        assert {entity.entity_kind for entity in entities} == {"film"}


def test_reference_candidates_are_balanced_by_year_and_deduplicated() -> None:
    queries: list[str] = []

    def fake_runner(query: str) -> list[dict]:
        queries.append(query)
        if "= 2024" in query:
            return [
                {"film": {"value": "http://www.wikidata.org/entity/Q1"}, "sitelinkCount": {"value": "40"}},
                {"film": {"value": "http://www.wikidata.org/entity/Q2"}, "sitelinkCount": {"value": "30"}},
            ]
        return [
            {"film": {"value": "http://www.wikidata.org/entity/Q1"}, "sitelinkCount": {"value": "40"}},
            {"film": {"value": "http://www.wikidata.org/entity/Q3"}, "sitelinkCount": {"value": "20"}},
        ]

    candidates = fetch_reference_candidates(5, 2024, 2025, run_query=fake_runner)

    assert [item.wikidata_id for item in candidates] == ["Q1", "Q2", "Q3"]
    assert len(queries) == 2
    assert all("LIMIT 3" in query or "LIMIT 2" in query for query in queries)
