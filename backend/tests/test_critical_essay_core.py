import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CanonicalEntity,
    CriticalClaim,
    CriticalClaimAnchor,
    CriticalWork,
    CriticalWorkSubject,
    DataSource,
    LanguageEdition,
    RawIngestionRun,
    ReferenceCollection,
    ReferenceCollectionMembership,
    SourceAssertion,
    SourceObject,
    SourceSnapshot,
)
from app.services.critical_sources import CRITICAL_SOURCE_REGISTRY, register_critical_sources
from app.services.critical_work_manifest import CriticalManifestError, import_manifest
from app.services import openalex_critical_discovery
from app.services import crossref_critical_discovery
from app.services.repair_canonical_entities import repair_unknown_films
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def add_fixture_collection(db: Session, code: str) -> None:
    if db.get(LanguageEdition, "en") is None:
        db.add(LanguageEdition(
            code="en", display_name="English", native_name="English", script="Latin", enabled=True, status="live",
        ))
    db.add(ReferenceCollection(
        code=code,
        title=f"{code} fixture collection",
        description="A local PostgreSQL test collection.",
        language_code="en",
        selection_method="recorded fixture",
        selection_version="v1",
    ))
    db.flush()


def test_critical_source_registry_is_idempotent_and_policy_only() -> None:
    engine = isolated_postgres_engine()
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
    engine = isolated_postgres_engine()
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
    engine = isolated_postgres_engine()
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


def test_metadata_manifest_links_a_work_to_existing_canonical_films(tmp_path) -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    manifest = tmp_path / "critical-pilot.json"
    manifest.write_text(json.dumps({
        "manifest_version": "critical-pilot-v1",
        "works": [{
            "source": {
                "name": "Fixture journal", "url": "https://fixture.test/article", "source_type": "peer_reviewed_critical_essays",
                "license": "CC BY 4.0", "rights_status": "attributed_reuse",
            },
            "external_id": "doi:fixture", "title": "Fixture critical work", "canonical_url": "https://fixture.test/article",
            "authors": ["Test Critic"], "published_on": "2024-04-09", "work_kind": "academic_article",
            "rights_scope": "metadata_link_only", "work_license": "CC BY 4.0", "language_code": "en",
            "subjects": [{"wikidata_id": "Qfixture", "role": "primary"}],
        }],
    }), encoding="utf-8")
    with Session(engine) as db:
        db.add(CanonicalEntity(entity_kind="film", canonical_label="Fixture film", wikidata_id="Qfixture"))
        db.commit()
        assert import_manifest(db, manifest) == {"works_created": 1, "works_reused": 0, "subject_links_created": 1}
        assert import_manifest(db, manifest) == {"works_created": 0, "works_reused": 1, "subject_links_created": 0}
        db.commit()
        work = db.scalar(select(CriticalWork))
        assert work is not None
        assert work.source_snapshot_id is None
        assert work.rights_scope == "metadata_link_only"
        assert db.scalar(select(func.count()).select_from(CriticalWorkSubject)) == 1


def test_metadata_manifest_refuses_full_text_without_acquisition_path(tmp_path) -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    manifest = tmp_path / "not-metadata-only.json"
    manifest.write_text(json.dumps({"manifest_version": "critical-pilot-v1", "works": []}), encoding="utf-8")
    with Session(engine) as db:
        db.add(CanonicalEntity(entity_kind="film", canonical_label="Fixture film", wikidata_id="Qfixture"))
        db.commit()
        manifest.write_text(json.dumps({
            "manifest_version": "critical-pilot-v1",
            "works": [{
                "source": {"name": "Fixture", "url": "https://fixture.test", "source_type": "essay", "license": "CC BY", "rights_status": "attributed_reuse"},
                "external_id": "fixture", "title": "Fixture", "canonical_url": "https://fixture.test", "authors": ["A"],
                "work_kind": "essay", "rights_scope": "full_text_reusable", "work_license": "CC BY", "language_code": "en",
                "subjects": [{"wikidata_id": "Qfixture", "role": "primary"}],
            }],
        }), encoding="utf-8")
        with pytest.raises(CriticalManifestError, match="metadata_link_only"):
            import_manifest(db, manifest)


def test_openalex_discovery_creates_review_candidates_but_never_fetches_full_text(tmp_path) -> None:
    recorded_work = {
        "id": "https://openalex.org/Wfixture",
        "title": "Virtuality and Reality in The Matrix",
        "doi": "https://doi.org/10.fixture/matrix",
        "publication_date": "2024-01-01",
        "authorships": [{"author": {"display_name": "Test Scholar"}}],
        "primary_location": {"landing_page_url": "https://fixture.test/matrix", "license": "cc-by"},
        "best_oa_location": {"landing_page_url": "https://fixture.test/matrix", "license": "cc-by", "pdf_url": "https://fixture.test/matrix.pdf"},
        "open_access": {"is_oa": True, "oa_status": "gold"},
        "language": "en", "cited_by_count": 12, "type": "article",
        "abstract_inverted_index": {"The": [0], "Matrix": [1], "examines": [2], "reality": [3]},
    }
    queried_titles: list[str] = []

    def recorded_works(title: str) -> list[dict]:
        queried_titles.append(title)
        return [recorded_work] if title == "The Matrix" else []

    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        matrix = CanonicalEntity(entity_kind="film", canonical_label="The Matrix", wikidata_id="Q83495")
        her = CanonicalEntity(entity_kind="film", canonical_label="Her", wikidata_id="Q999")
        no_match = CanonicalEntity(entity_kind="film", canonical_label="No Match Film", wikidata_id="Q998")
        db.add_all([matrix, her, no_match])
        db.flush()
        add_fixture_collection(db, "fixture-collection")
        db.add_all([
            ReferenceCollectionMembership(collection_code="fixture-collection", entity_id=matrix.id, selection_position=1, selection_signals={}, source_reference="fixture"),
            ReferenceCollectionMembership(collection_code="fixture-collection", entity_id=her.id, selection_position=2, selection_signals={}, source_reference="fixture"),
            ReferenceCollectionMembership(collection_code="fixture-collection", entity_id=no_match.id, selection_position=3, selection_signals={}, source_reference="fixture"),
        ])
        db.commit()
        result = openalex_critical_discovery.discover(
            db, collection_code="fixture-collection", progress_every=3,
            work_fetcher=recorded_works, storage_root=tmp_path / "snapshots", delay_seconds=0,
        )
        db.commit()

        assert result == {"requested": 3, "queried": 2, "skipped_ambiguous": 1, "no_candidates": 1, "candidates": 1, "snapshots": 1}
        candidate = db.scalar(select(openalex_critical_discovery.CriticalDiscoveryCandidate))
        assert candidate is not None
        assert candidate.review_status == "pending"
        assert candidate.metadata_json["open_access"]["pdf_url"] == "https://fixture.test/matrix.pdf"
        assert candidate.source_snapshot_id is not None
        assert queried_titles == ["The Matrix", "No Match Film"]
        assert openalex_critical_discovery.quality_report(db, "fixture-collection") == {
            "collection_films": 3, "checked": 3, "candidates": 1,
            "complete": 1, "no_candidates": 1, "skipped_ambiguous": 1, "failed": 0,
        }
        rerun = openalex_critical_discovery.discover(
            db, collection_code="fixture-collection", progress_every=1,
            work_fetcher=recorded_works, storage_root=tmp_path / "snapshots", delay_seconds=0,
        )
        assert rerun["requested"] == 0
        assert queried_titles == ["The Matrix", "No Match Film"]


def test_crossref_discovery_retains_bibliographic_metadata_not_abstracts(tmp_path) -> None:
    raw_work = {
        "DOI": "10.fixture/godfather",
        "title": ["The Godfather and the American Dream"],
        "URL": "https://doi.org/10.fixture/godfather",
        "type": "journal-article",
        "published": {"date-parts": [[2024, 1, 1]]},
        "author": [{"given": "Test", "family": "Scholar"}],
        "container-title": ["Fixture Studies"],
        "publisher": "Fixture Press",
        "abstract": "This copyrighted abstract must never be persisted.",
        "license": [{"URL": "https://creativecommons.org/licenses/by/4.0/"}],
    }
    recorded_work = crossref_critical_discovery.safe_work(raw_work)
    assert recorded_work is not None
    assert "abstract" not in recorded_work

    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        film = CanonicalEntity(entity_kind="film", canonical_label="The Godfather", wikidata_id="Q47703")
        db.add(film)
        db.flush()
        add_fixture_collection(db, "fixture-crossref")
        db.add(ReferenceCollectionMembership(
            collection_code="fixture-crossref", entity_id=film.id, selection_position=1,
            selection_signals={}, source_reference="fixture",
        ))
        db.commit()
        result = crossref_critical_discovery.discover(
            db, collection_code="fixture-crossref", work_fetcher=lambda _title: [recorded_work],
            storage_root=tmp_path / "snapshots", delay_seconds=0,
        )
        db.commit()

        assert result == {"requested": 1, "queried": 1, "skipped_ambiguous": 0, "timeouts": 0, "no_candidates": 0, "candidates": 1, "snapshots": 1}
        candidate = db.scalar(select(crossref_critical_discovery.CriticalDiscoveryCandidate))
        assert candidate is not None
        assert candidate.provider == "crossref"
        assert candidate.metadata_json["doi"] == "10.fixture/godfather"
        assert "abstract" not in candidate.metadata_json
        snapshot_record = db.get(SourceSnapshot, candidate.source_snapshot_id)
        assert snapshot_record is not None
        assert snapshot_record.storage_uri is not None
        assert "abstract" not in Path(snapshot_record.storage_uri.removeprefix("file://")).read_text(encoding="utf-8")


def test_crossref_timeout_is_recorded_and_does_not_abort_other_titles(tmp_path) -> None:
    def recorded_works(title: str) -> list[dict]:
        if title == "Timeout Film":
            raise httpx.ReadTimeout("fixture timeout")
        return []

    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        timeout = CanonicalEntity(entity_kind="film", canonical_label="Timeout Film", wikidata_id="Qtimeout")
        empty = CanonicalEntity(entity_kind="film", canonical_label="Empty Film", wikidata_id="Qempty")
        db.add_all([timeout, empty])
        db.flush()
        add_fixture_collection(db, "fixture-timeout")
        db.add_all([
            ReferenceCollectionMembership(collection_code="fixture-timeout", entity_id=timeout.id, selection_position=1, selection_signals={}, source_reference="fixture"),
            ReferenceCollectionMembership(collection_code="fixture-timeout", entity_id=empty.id, selection_position=2, selection_signals={}, source_reference="fixture"),
        ])
        db.commit()
        result = crossref_critical_discovery.discover(
            db, collection_code="fixture-timeout", work_fetcher=recorded_works,
            storage_root=tmp_path / "snapshots", delay_seconds=0,
        )
        db.commit()

        assert result == {"requested": 2, "queried": 1, "skipped_ambiguous": 0, "timeouts": 1, "no_candidates": 1, "candidates": 0, "snapshots": 0}
        queries = {query.query_title: query for query in db.scalars(select(crossref_critical_discovery.CriticalDiscoveryQuery))}
        assert queries["Timeout Film"].status == "failed"
        assert "ReadTimeout" in queries["Timeout Film"].error_summary
        assert queries["Empty Film"].status == "no_candidates"


def test_canonical_repair_uses_retained_wikidata_p31_not_title_guessing() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        source = DataSource(name="Wikidata fixture", url="https://wikidata.org", source_type="metadata", license="CC0", rights_status="open")
        unknown = CanonicalEntity(entity_kind="unknown_work", canonical_label="Qfixture", wikidata_id="Qfixture")
        db.add_all([source, unknown])
        db.flush()
        run = RawIngestionRun(source_id=source.id, adapter_name="fixture", adapter_version="1", status="complete")
        obj = SourceObject(source_id=source.id, external_id="Qfixture", object_kind="wikibase_item", canonical_url="https://wikidata.org/wiki/Qfixture")
        db.add_all([run, obj])
        db.flush()
        snap = SourceSnapshot(source_object_id=obj.id, ingestion_run_id=run.id, canonical_url=obj.canonical_url, content_hash="b" * 64, license="CC0")
        db.add(snap)
        db.flush()
        db.add(SourceAssertion(
            source_snapshot_id=snap.id,
            statement_locator="claims.P31[0]",
            source_property="P31",
            raw_subject={"wikidata_id": "Qfixture", "label": "Corrected Film"},
            raw_value={"datavalue": {"value": {"id": "Q11424"}}},
            raw_qualifiers={},
            extractor_version="fixture",
        ))
        db.commit()
        assert repair_unknown_films(db) == {"inspected_unknown_work": 1, "repaired_films": 1}
        db.commit()
        assert unknown.entity_kind == "film"
        assert unknown.canonical_label == "Corrected Film"
