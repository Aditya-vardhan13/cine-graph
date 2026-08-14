from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.models import CanonicalEntity, NarrativePassage, ResearchAnswer, ResearchAnswerEvidence
from app.services.wikipedia_research import chunk_section, clean_wikitext, split_sections


def test_section_parser_retains_hierarchy_and_excludes_reference_material() -> None:
    source = """Lead prose with <ref name=lead />.\n== Plot ==\nA [[Hero|hero]] acts.\n=== Ending ===\nThe ending follows.\n== References ==\n* cite material\n"""
    sections = split_sections(source)
    assert [(section["locator"], section["title"]) for section in sections] == [
        ("lead", "Lead"), ("plot", "Plot"), ("plot/ending", "Plot / Ending"),
    ]
    assert clean_wikitext(str(sections[1]["content"])) == "A hero acts."
    assert list(chunk_section("One paragraph.\n\nSecond paragraph.", limit=16)) == ["One paragraph.", "Second paragraph."]


def test_research_answer_requires_a_retained_evidence_target() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        film = CanonicalEntity(entity_kind="film", canonical_label="Fixture")
        db.add(film)
        db.flush()
        answer = ResearchAnswer(
            subject_entity_id=film.id,
            question_id="fixture.question",
            question_text="Fixture question?",
            answer="Fixture answer.",
            evidence_class="narrative_extraction",
            answer_version="test",
        )
        db.add(answer)
        db.flush()
        evidence = ResearchAnswerEvidence(research_answer_id=answer.id)
        db.add(evidence)
        # SQLite enforces this check too: the evidence cannot be targetless.
        try:
            db.commit()
        except Exception:
            db.rollback()
        else:
            raise AssertionError("research-answer evidence must have a passage or source assertion")
        assert db.scalar(select(NarrativePassage)) is None
