"""Mixed adapters use one explicitly configured current extraction per source."""
import hashlib

import pytest
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import (CanonicalEntity, DataSource, EvidenceChunk, LanguageEdition,
                        NarrativePassage, NarrativeUseDecision, ReferenceCollection,
                        ReferenceCollectionMembership, SourceObject, SourceSnapshot)
from app.services.evidence_preprocessing import ChunkConfiguration, build_evidence_chunks
from app.services.hybrid_evidence_retrieval import _section_conditions
from tests.postgres_test_db import isolated_postgres_engine


pytestmark = pytest.mark.integration


def test_mixed_source_versions_keep_only_current_extraction_per_snapshot():
    engine = isolated_postgres_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(LanguageEdition(code="en", display_name="English", script="Latin", enabled=True, status="active"))
        db.add(ReferenceCollection(code="mixed-source-fixture", title="Mixed", description="Test only",
                                   language_code="en", selection_method="fixture", selection_version="v1"))
        source = DataSource(name="Mixed source fixture", url="https://en.wikipedia.org/",
                            source_type="wiki", license="CC BY-SA 4.0", rights_status="attributed_reuse")
        db.add(source)
        db.flush()
        expected_passages = []
        for number, parser, versions, section in [
            (1, "enwiki-pinned-revision-recovery-v1", ["enwiki-section-passages-recovered-v1"], "plot-summary"),
            (2, "enwiki-article-html-capture-v1", ["enwiki-article-html-extraction-v1", "enwiki-article-html-extraction-v7"], "synopsis"),
        ]:
            entity = CanonicalEntity(canonical_label=f"Fixture {number}", entity_kind="film")
            db.add(entity)
            db.flush()
            db.add(ReferenceCollectionMembership(collection_code="mixed-source-fixture", entity_id=entity.id,
                                                  source_reference="fixture", status="included"))
            url = f"https://en.wikipedia.org/wiki/Fixture_{number}"
            obj = SourceObject(source_id=source.id, external_id=str(number), object_kind="article", canonical_url=url)
            db.add(obj)
            db.flush()
            snapshot = SourceSnapshot(source_object_id=obj.id, source_revision="1", canonical_url=url,
                                      attribution_url=url, parser_version=parser, content_hash="a" * 64,
                                      storage_uri="file:///fixture", license="CC BY-SA 4.0", fetch_status="success")
            db.add(snapshot)
            db.flush()
            db.add(NarrativeUseDecision(source_snapshot_id=snapshot.id, use_case="semantic_index_and_model_input",
                                        decision="approved", decision_version=1, reviewer="fixture",
                                        decision_basis_url="https://creativecommons.org/licenses/by-sa/4.0/",
                                        decision_notes="Isolated test approval only."))
            for version in versions:
                content = (f"Film {number} version {version} follows a character choosing between loyalty and duty. " * 8)
                passage = NarrativePassage(subject_entity_id=entity.id, source_snapshot_id=snapshot.id,
                                           section_locator=section, section_title=section.title(), ordinal=0,
                                           language_code="en", content=content,
                                           content_hash=hashlib.sha256(content.encode()).hexdigest(),
                                           citation_markers=[], extraction_version=version)
                db.add(passage)
                db.flush()
                if version == versions[-1]:
                    expected_passages.append(passage.id)
        db.commit()
        with pytest.raises(ValueError, match="multiple source parser versions"):
            build_evidence_chunks(db, collection_code="mixed-source-fixture")
        result = build_evidence_chunks(db, collection_code="mixed-source-fixture",
                                       config=ChunkConfiguration(current_extractions_per_snapshot=True))
        chunks = db.scalars(select(EvidenceChunk).where(EvidenceChunk.preprocessing_run_id == result["run_id"],
                                                        EvidenceChunk.quality_status == "eligible")).all()
        assert {chunk.narrative_passage_id for chunk in chunks} == set(expected_passages)
        conditions = _section_conditions(question_id="story.cross_film_comparison", evidence_class="narrative_extraction")
        routed = db.scalars(select(EvidenceChunk).where(EvidenceChunk.preprocessing_run_id == result["run_id"],
                                                        or_(*conditions))).all()
        assert {chunk.narrative_passage_id for chunk in routed} == set(expected_passages)
        repeat = build_evidence_chunks(db, collection_code="mixed-source-fixture",
                                       config=ChunkConfiguration(current_extractions_per_snapshot=True))
        assert result["run_id"] == repeat["run_id"]
    engine.dispose()


def test_current_policy_is_distinct_and_cannot_be_combined_with_manual_filters():
    assert "current_extractions_per_snapshot" not in ChunkConfiguration().payload
    assert ChunkConfiguration(current_extractions_per_snapshot=True).digest != ChunkConfiguration().digest
    with pytest.raises(ValueError, match="cannot be combined"):
        ChunkConfiguration(current_extractions_per_snapshot=True, extraction_version="v1")
