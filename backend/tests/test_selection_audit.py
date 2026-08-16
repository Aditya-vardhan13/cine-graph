import pytest
from sqlalchemy.orm import Session

from app.db import Base
from app.services.selection_audit import audit_selection, wikipedia_release_years
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_audit_requires_unique_qid_film_type_and_year() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        report = audit_selection(db, [{"position": 1, "title": "Example", "release_year": 2001}], ["file:///missing.json"])
    assert report["pass"] is False
    assert report["verified_identity_type_year"] == 0
    assert report["missing"][0]["title"] == "Example"


def test_audit_extracts_release_year_only_from_infobox_release() -> None:
    payload = {
        "page": {"revisions": [{"slots": {"main": {"content": """\
| released = {{Film date|2012|04|20}}
The film was discussed again in 2024.
"""}}}]},
    }
    assert wikipedia_release_years(payload) == {2012}
