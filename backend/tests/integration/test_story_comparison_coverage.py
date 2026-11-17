"""The comparison must not mistake unreviewed corpus coverage for relevance."""
import hashlib

from sqlalchemy.orm import Session

from app.db import Base
from app.models import (CanonicalEntity, DataSource, EvidenceChunk, EvidenceChunkRun, Film,
                        LanguageEdition, NarrativePassage, NarrativeUseDecision,
                        ReferenceCollection, ReferenceCollectionMembership, SourceObject, SourceSnapshot)
from app.services.story_comparison import compare_story_evidence
from tests.postgres_test_db import isolated_postgres_engine


def test_unreviewed_film_is_reported_as_coverage_gap():
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", script="Latin", enabled=True, status="active"))
        db.add(ReferenceCollection(code="coverage-fixture", title="Coverage", description="Isolated test",
                                   language_code="en", selection_method="fixture", selection_version="v1"))
        source = DataSource(name="Fixture Wikipedia", url="https://en.wikipedia.org/", source_type="wiki",
                            license="CC BY-SA 4.0", rights_status="attributed_reuse")
        db.add(source)
        db.flush()
        run = EvidenceChunkRun(collection_code="coverage-fixture", language_code="en", chunker_version="v1",
                               configuration={}, configuration_hash="a" * 64, status="complete")
        db.add(run)
        db.flush()
        entities = []
        snapshots = []
        for title in ("First Film", "Second Film"):
            entity = CanonicalEntity(canonical_label=title, entity_kind="film")
            db.add(entity)
            db.flush()
            entities.append(entity.id)
            db.add(Film(entity_id=entity.id, canonical_title=title, original_language_code="en"))
            db.add(ReferenceCollectionMembership(collection_code="coverage-fixture", entity_id=entity.id,
                                                  source_reference="test", status="included"))
            url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
            obj = SourceObject(source_id=source.id, external_id=title, object_kind="article", canonical_url=url)
            db.add(obj)
            db.flush()
            snapshot = SourceSnapshot(source_object_id=obj.id, canonical_url=url, attribution_url=url,
                                      content_hash="b" * 64, byte_size=10, storage_uri="file:///test",
                                      license="CC BY-SA 4.0", fetch_status="success")
            db.add(snapshot)
            db.flush()
            snapshots.append(snapshot)
            content = "A family protects each other during a conflict."
            passage = NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=snapshot.id,
                                       section_locator="plot", section_title="Plot", ordinal=0,
                                       language_code="en", content=content,
                                       content_hash=hashlib.sha256(content.encode()).hexdigest(),
                                       citation_markers=[], extraction_version="fixture-v1")
            db.add(passage)
            db.flush()
            db.add(EvidenceChunk(preprocessing_run_id=run.id, narrative_passage_id=passage.id,
                                 subject_entity_id=entity.id, source_snapshot_id=snapshot.id,
                                 language_code="en", section_locator="plot", section_title="Plot",
                                 chunk_ordinal=0, content=content, content_hash=passage.content_hash,
                                 word_count=8, token_count_estimate=10, sentence_count=1,
                                 quality_status="eligible", chunker_version="v1", configuration_hash="a" * 64))
        db.add(NarrativeUseDecision(source_snapshot_id=snapshots[0].id, use_case="semantic_index_and_model_input",
                                    decision="approved", decision_version=1,
                                    decision_basis_url="https://creativecommons.org/licenses/by-sa/4.0/",
                                    decision_notes="Isolated test approval only.", reviewer="test"))
        db.commit()
        result = compare_story_evidence(db, first_entity_id=entities[0], second_entity_id=entities[1],
                                        question="How does family respond to conflict?",
                                        collection_code="coverage-fixture")
        assert result.answerability_status == "insufficient_evidence"
        assert result.retrieval_method == "not_run"
        assert "Second Film" in result.answerability_reason
        assert "not a judgment" in result.caution
        assert not result.lenses
    engine.dispose()
