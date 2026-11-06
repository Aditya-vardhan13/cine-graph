"""Real PostgreSQL and FastAPI coverage for append-only rights decisions."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admin_rights import router
from app.db import Base, get_db
from app.models import (
    CanonicalEntity,
    DataSource,
    NarrativePassage,
    NarrativeUseDecision,
    SourceObject,
    SourceSnapshot,
)
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_review_api_records_per_snapshot_versions_and_latest_decision_wins():
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    app = FastAPI()

    def real_test_session():
        with Session(engine) as db:
            yield db

    app.include_router(router)
    app.dependency_overrides[get_db] = real_test_session
    headers = {"x-operator-email": "adityavk1310@gmail.com"}
    with Session(engine) as db:
        source = DataSource(
            name="Rights queue retained source", url="https://en.wikipedia.org/",
            source_type="wiki", license="CC BY-SA 4.0", rights_status="attributed_reuse",
        )
        film = CanonicalEntity(canonical_label="Review Queue Film", entity_kind="film")
        db.add_all([source, film])
        db.flush()
        source_object = SourceObject(
            source_id=source.id, external_id="Review_Queue_Film", object_kind="article",
            canonical_url="https://en.wikipedia.org/wiki/Review_Queue_Film",
        )
        db.add(source_object)
        db.flush()
        snapshot = SourceSnapshot(
            source_object_id=source_object.id, source_revision="fixture-rev-1",
            canonical_url=source_object.canonical_url, attribution_url=source_object.canonical_url,
            content_hash="a" * 64, license="CC BY-SA 4.0", fetch_status="success",
        )
        db.add(snapshot)
        db.flush()
        db.add(NarrativePassage(
            subject_entity_id=film.id, source_snapshot_id=snapshot.id,
            section_locator="plot", section_title="Plot", ordinal=0,
            language_code="en", content="A retained plot passage for an API rights review fixture.",
            content_hash="b" * 64, citation_markers=[], extraction_version="fixture-v1",
        ))
        second_snapshot = SourceSnapshot(
            source_object_id=source_object.id, source_revision="fixture-rev-2",
            canonical_url=source_object.canonical_url, attribution_url=source_object.canonical_url,
            content_hash="c" * 64, license="CC BY-SA 4.0", fetch_status="success",
        )
        db.add(second_snapshot)
        db.flush()
        db.add(NarrativePassage(
            subject_entity_id=film.id, source_snapshot_id=second_snapshot.id,
            section_locator="production", section_title="Production", ordinal=0,
            language_code="en", content="A second captured revision must receive its own review decision.",
            content_hash="d" * 64, citation_markers=[], extraction_version="fixture-v1",
        ))
        db.commit()
        snapshot_id = snapshot.id
        second_snapshot_id = second_snapshot.id

    with TestClient(app) as client:
        assert client.get("/api/v1/admin/rights/queue").status_code == 401
        assert client.get("/api/v1/admin/rights/queue",
                          headers={"x-operator-email": "someone-else@example.com"}).status_code == 401
        queue = client.get("/api/v1/admin/rights/queue", headers=headers)
        assert queue.status_code == 200
        assert queue.json()["total"] == 2
        assert queue.json()["offset"] == 0
        item = next(row for row in queue.json()["items"] if row["snapshot_id"] == str(snapshot_id))
        assert item["snapshot_id"] == str(snapshot_id)
        assert item["latest_decision"] is None
        assert item["films"] == ["Review Queue Film"]
        assert item["samples"][0]["section"] == "plot"
        first_page = client.get("/api/v1/admin/rights/queue?limit=1&offset=0", headers=headers).json()
        second_page = client.get("/api/v1/admin/rights/queue?limit=1&offset=1", headers=headers).json()
        assert first_page["total"] == second_page["total"] == 2
        first_id = first_page["items"][0]["snapshot_id"]
        second_id = second_page["items"][0]["snapshot_id"]
        assert first_id != second_id
        assert {first_id, second_id} == {str(snapshot_id), str(second_snapshot_id)}

        missing_basis = client.post(f"/api/v1/admin/rights/{snapshot_id}", headers=headers,
                                    json={"decision": "approved", "decision_notes": "Reviewed scope."})
        assert missing_basis.status_code == 422

        approved = client.post(f"/api/v1/admin/rights/{snapshot_id}", headers=headers, json={
            "decision": "approved",
            "decision_basis_url": "https://creativecommons.org/licenses/by-sa/4.0/",
            "decision_notes": "Reviewed applicable license and intended local model-input scope.",
        })
        assert approved.status_code == 200
        assert approved.json()["latest_decision"]["version"] == 1
        after_one_approval = client.get("/api/v1/admin/rights/queue", headers=headers).json()["items"]
        other_revision = next(row for row in after_one_approval
                              if row["snapshot_id"] == str(second_snapshot_id))
        assert other_revision["latest_decision"] is None

        denied = client.post(f"/api/v1/admin/rights/{snapshot_id}", headers=headers, json={
            "decision": "denied", "decision_notes": "New review found scope uncertain; exclude it.",
        })
        assert denied.status_code == 200
        assert denied.json()["latest_decision"]["version"] == 2

        refreshed = client.get("/api/v1/admin/rights/queue", headers=headers)
        current = next(row for row in refreshed.json()["items"]
                       if row["snapshot_id"] == str(snapshot_id))["latest_decision"]
        assert current["decision"] == "denied"
        assert current["version"] == 2

    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(NarrativeUseDecision).where(
            NarrativeUseDecision.source_snapshot_id == snapshot_id,
        )) == 2
    engine.dispose()
