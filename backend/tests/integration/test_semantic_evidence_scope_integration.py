"""The shared semantic scope rechecks the latest rights state in PostgreSQL."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (
    CanonicalEntity,
    DataSource,
    EvidenceChunk,
    EvidenceChunkRun,
    LanguageEdition,
    NarrativePassage,
    NarrativeUseDecision,
    ReferenceCollection,
    SourceObject,
    SourceSnapshot,
)
from app.services.semantic_evidence_scope import semantically_approved_chunk_ids
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_scope_excludes_stale_or_ineligible_snapshot_rights() -> None:
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            source = DataSource(
                name="Semantic scope source", url="https://example.test/",
                source_type="fixture", license="CC BY-SA 4.0", rights_status="attributed_reuse",
            )
            film = CanonicalEntity(entity_kind="film", canonical_label="Rights Scope Film")
            language = LanguageEdition(code="en", display_name="English", enabled=True, status="active")
            db.add_all([source, film, language])
            db.flush()
            collection = ReferenceCollection(
                code="rights-scope-test", title="Rights scope test", description="Integration fixture",
                language_code="en", selection_method="fixture", selection_version="v1",
            )
            db.add(collection)
            db.flush()
            run = EvidenceChunkRun(
                collection_code=collection.code, language_code="en", chunker_version="fixture-v1",
                configuration={}, configuration_hash="f" * 64, status="complete",
            )
            db.add(run)
            db.flush()

            fixtures = [
                ("valid", "CC BY-SA 4.0", "https://example.test/attribution",
                 "https://example.test/policy", ["approved"]),
                ("later-denied", "CC BY-SA 4.0", "https://example.test/attribution",
                 "https://example.test/policy", ["approved", "denied"]),
                ("wrong-license", "CC BY-NC 4.0", "https://example.test/attribution",
                 "https://example.test/policy", ["approved"]),
                ("http-attribution", "CC BY-SA 4.0", "http://example.test/attribution",
                 "https://example.test/policy", ["approved"]),
                ("hostless-basis", "CC BY-SA 4.0", "https://example.test/attribution",
                 "https:///missing-host", ["approved"]),
                ("credentialed-attribution", "CC BY-SA 4.0",
                 "https://user:secret@example.test/attribution",
                 "https://example.test/policy", ["approved"]),
                ("credentialed-basis", "CC BY-SA 4.0", "https://example.test/attribution",
                 "https://user:secret@example.test/policy", ["approved"]),
            ]
            chunk_ids = {}
            for name, license_name, attribution, basis, decisions in fixtures:
                source_object = SourceObject(
                    source_id=source.id, external_id=name, object_kind="article",
                    canonical_url="https://example.test/" + name,
                )
                db.add(source_object)
                db.flush()
                snapshot = SourceSnapshot(
                    source_object_id=source_object.id, source_revision="rev-1",
                    canonical_url=source_object.canonical_url, attribution_url=attribution,
                    content_hash=(name.encode().hex() + "0" * 64)[:64], license=license_name,
                    fetch_status="success",
                )
                db.add(snapshot)
                db.flush()
                passage = NarrativePassage(
                    subject_entity_id=film.id, source_snapshot_id=snapshot.id,
                    section_locator="plot", section_title="Plot", ordinal=len(chunk_ids),
                    language_code="en", content=f"Evidence for {name}.",
                    content_hash=("a" * 63 + str(len(chunk_ids))),
                    citation_markers=[], extraction_version="fixture-v1",
                )
                db.add(passage)
                db.flush()
                chunk = EvidenceChunk(
                    preprocessing_run_id=run.id, narrative_passage_id=passage.id,
                    subject_entity_id=film.id, source_snapshot_id=snapshot.id,
                    language_code="en", section_locator="plot", section_title="Plot",
                    chunk_ordinal=0, content=f"Evidence for {name}.",
                    content_hash=("b" * 63 + str(len(chunk_ids))), word_count=3,
                    token_count_estimate=3, sentence_count=1, quality_status="eligible",
                    quality_flags=[], chunker_version="fixture-v1", configuration_hash="f" * 64,
                )
                db.add(chunk)
                db.flush()
                chunk_ids[name] = chunk.id
                for version, decision in enumerate(decisions, start=1):
                    db.add(NarrativeUseDecision(
                        source_snapshot_id=snapshot.id, use_case="semantic_index_and_model_input",
                        decision=decision, decision_version=version,
                        decision_basis_url=basis, decision_notes="Reviewed intended use scope.",
                        reviewer="reviewer@example.test",
                    ))
            db.flush()

            eligible_ids = set(db.scalars(semantically_approved_chunk_ids()).all())
            assert eligible_ids == {chunk_ids["valid"]}
    finally:
        engine.dispose()
