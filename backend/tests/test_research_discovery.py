"""Pure discovery policy checks; live retrieval belongs to isolated integration tests."""
from uuid import uuid4

from app.models import EvidenceChunk
from app.services.research_discovery import (
    _has_required_topic_cues, _passage_alignment, _rank_leads,
)


def _chunk(film_id, content):
    return EvidenceChunk(
        id=uuid4(), subject_entity_id=film_id, content=content,
        section_title="Plot",
    )


def test_question_terms_ignore_stopwords_and_match_whole_words() -> None:
    question = "Which films make a human and artificial intelligence partners?"
    assert _passage_alignment(question, "The artificial intelligence becomes a partner.") == 2
    assert _passage_alignment(question, "The forest has a film about humanities.") == 0


def test_explicit_topic_cue_prevents_generic_semantic_matches() -> None:
    question = "Which films make a human and artificial intelligence partners?"
    assert _has_required_topic_cues(question, "A human forms a bond with an AI operating system.")
    assert not _has_required_topic_cues(question, "A human forms a bond with a stranger.")
    assert _has_required_topic_cues("How does power corrupt a hero?", "A hero changes.")


def test_discovery_ranks_one_attributable_passage_per_film_and_respects_exclusions() -> None:
    first_film, second_film, excluded_film = uuid4(), uuid4(), uuid4()
    first = _chunk(first_film, "An AI companion forms a relationship with a lonely writer.")
    duplicate = _chunk(first_film, "A machine companion changes the writer's life.")
    second = _chunk(second_film, "An android discovers what it means to be human.")
    unrelated = _chunk(uuid4(), "A strange creature attacks a group of humans.")
    excluded = _chunk(excluded_film, "An AI robot changes its human companion.")
    results = _rank_leads(
        question="Which films make an AI companion a human partner?",
        semantic=[unrelated, first, duplicate, second, excluded],
        lexical=[first, duplicate, second, excluded],
        excluded={excluded_film}, limit=6,
    )
    assert {chunk.subject_entity_id for chunk, _ in results} == {first_film, second_film}
    assert results[0][0].id == first.id
    assert results[0][1] == ("semantic", "term_rerank")
