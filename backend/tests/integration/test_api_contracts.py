"""Real HTTP and PostgreSQL contract checks for the isolated local stack."""
from __future__ import annotations

import os

import httpx
import pytest
from sqlalchemy import create_engine, text


API_URL = os.environ.get("CINEGRAPH_INTEGRATION_API_URL", "http://127.0.0.1:8001")
DATABASE_URL = os.environ.get(
    "CINEGRAPH_TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/cinegraph_test",
)
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("CINEGRAPH_RUN_INTEGRATION") != "1",
        reason="run through scripts/run_integration_tests.sh against the isolated local stack",
    ),
]


def api_get(path: str) -> httpx.Response:
    return httpx.get(f"{API_URL}{path}", timeout=5.0)


def test_health_and_catalogue_are_served_from_real_postgresql() -> None:
    response = api_get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["films"] == 2
    assert payload["language_editions"] == [{
        "code": "en", "display_name": "English", "native_name": "English",
        "script": "Latin", "enabled": True, "status": "live", "transliteration_strategy": None,
    }]

    with create_engine(DATABASE_URL).connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM films")) == 2
        assert connection.scalar(text("SELECT count(*) FROM film_provenance")) == 2
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260816_11"
        assert connection.scalar(text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")) is True
        assert connection.scalar(text("SELECT to_regclass('public.ix_films_canonical_title_trgm')")) == "ix_films_canonical_title_trgm"


def test_search_detail_comparison_and_lineage_return_evidence_backed_contracts() -> None:
    search = api_get("/api/v1/films?q=dark&limit=5")
    assert search.status_code == 200
    items = search.json()
    assert [item["title"] for item in items] == ["The Dark Knight"]
    knight_id = items[0]["id"]

    detail = api_get(f"/api/v1/films/{knight_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["credits"] == [{
        "person_id": detail_payload["credits"][0]["person_id"],
        "name": "Christopher Nolan", "role": "director", "character_name": None,
    }]
    assert detail_payload["provenance"] == [{
        "source_name": "Integration fixture source",
        "source_url": "https://example.test/cinegraph-fixture",
        "license": "CC0 1.0",
        "field_name": "canonical_title",
        "source_reference": "https://www.wikidata.org/wiki/Q163872",
    }]

    begins = api_get("/api/v1/films?q=begins&limit=5").json()[0]
    comparison = api_get(f"/api/v1/films/compare?first_id={begins['id']}&second_id={knight_id}")
    assert comparison.status_code == 200
    labels = {signal["label"] for signal in comparison.json()["signals"]}
    assert labels == {"Shared genres", "Shared creative collaborators", "Release era"}

    lineage = api_get(f"/api/v1/films/{begins['id']}/lineage")
    assert lineage.status_code == 200
    edges = lineage.json()["edges"]
    assert len(edges) == 1
    assert edges[0]["target_title"] == "The Dark Knight"
    assert edges[0]["evidence_url"] == "https://www.wikidata.org/wiki/Q163872"
