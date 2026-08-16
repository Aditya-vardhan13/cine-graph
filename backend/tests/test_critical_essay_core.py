from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CanonicalEntity,
    CriticalClaim,
    CriticalClaimAnchor,
    CriticalWork,
    DataSource,
)
from app.services.critical_sources import CRITICAL_SOURCE_REGISTRY, register_critical_sources


def test_critical_source_registry_is_idempotent_and_policy_only() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = register_critical_sources(db)
        second = register_critical_sources(db)
        db.commit()

        assert first == {"created": len(CRITICAL_SOURCE_REGISTRY), "reused": 0, "registered": len(CRITICAL_SOURCE_REGISTRY)}
        assert second == {"created": 0, "reused": len(CRITICAL_SOURCE_REGISTRY), "registered": len(CRITICAL_SOURCE_REGISTRY)}
        assert db.scalar(select(func.count()).select_from(DataSource)) == len(CRITICAL_SOURCE_REGISTRY)
        medium = db.scalar(select(DataSource).where(DataSource.name == "Medium"))
        assert medium is not None
        assert medium.rights_status == "metadata_link_only"
        assert "Do not ingest article full text" in medium.notes


def test_reusable_critical_work_requires_a_licensed_snapshot() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = DataSource(name="Fixture criticism", url="https://fixture.test", source_type="essay", license="CC BY", rights_status="review_required")
        db.add(source)
        db.flush()
        db.add(CriticalWork(
            source_id=source.id,
            external_id="fixture-1",
            title="A reusable work without a snapshot",
            canonical_url="https://fixture.test/1",
            authors=["Test Author"],
            work_kind="essay",
            rights_scope="full_text_reusable",
        ))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("reusable critical work was accepted without an immutable licensed snapshot")


def test_link_only_claim_stays_attributed_and_requires_an_anchor_target() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = DataSource(name="Fixture criticism", url="https://fixture.test", source_type="essay", license="Author retained", rights_status="metadata_link_only")
        film = CanonicalEntity(entity_kind="film", canonical_label="Fixture film")
        db.add_all([source, film])
        db.flush()
        work = CriticalWork(
            source_id=source.id,
            external_id="fixture-essay",
            title="A reading of Fixture film",
            canonical_url="https://fixture.test/essay",
            authors=["Test Critic"],
            work_kind="essay",
            rights_scope="metadata_link_only",
            attribution_text="Test Critic, Fixture criticism",
        )
        db.add(work)
        db.flush()
        claim = CriticalClaim(
            critical_work_id=work.id,
            subject_entity_id=film.id,
            lens="power",
            claim_type="interpretive_argument",
            claim_text="The cited critic reads the protagonist's rise as a study of power.",
            source_claim_locator="section: Power",
        )
        db.add(claim)
        db.flush()
        db.add(CriticalClaimAnchor(critical_claim_id=claim.id, anchor_relation="narrative_anchor"))
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("critical claim anchor was accepted without a factual or narrative target")
