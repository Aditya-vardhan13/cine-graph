from app.services.retrieval_routing import (
    RetrievalLane,
    narrative_section_candidates,
    route_research_question,
)


def test_source_facts_route_to_assertions_with_lexical_fallback() -> None:
    route = route_research_question(question_id="production.imax", evidence_class="source_fact")

    assert route.primary is RetrievalLane.STRUCTURED
    assert route.candidates == (RetrievalLane.STRUCTURED, RetrievalLane.LEXICAL)


def test_story_questions_route_to_semantic_evidence() -> None:
    route = route_research_question(question_id="story.inciting-disruption", evidence_class="narrative_extraction")

    assert route.primary is RetrievalLane.NARRATIVE_SEMANTIC
    assert route.candidates == (RetrievalLane.NARRATIVE_SEMANTIC, RetrievalLane.LEXICAL)


def test_interpretations_do_not_fall_back_to_an_unattributed_fact() -> None:
    route = route_research_question(question_id="theme.terrorism", evidence_class="attributed_interpretation")

    assert route.primary is RetrievalLane.CRITICAL_INTERPRETATION
    assert route.candidates == (RetrievalLane.CRITICAL_INTERPRETATION, RetrievalLane.NARRATIVE_SEMANTIC)


def test_reviewed_evidence_class_takes_precedence_over_question_prefix() -> None:
    route = route_research_question(question_id="impact.reception", evidence_class="narrative_extraction")

    assert route.primary is RetrievalLane.NARRATIVE_SEMANTIC


def test_unclassified_question_starts_with_exact_evidence() -> None:
    route = route_research_question(question_id="unknown.custom-question")

    assert route.primary is RetrievalLane.LEXICAL


def test_narrative_section_candidates_are_declared_before_ranking() -> None:
    assert narrative_section_candidates(
        question_id="story.return", evidence_class="narrative_extraction",
    ) == ("plot",)
    assert narrative_section_candidates(
        question_id="structure.circular", evidence_class="narrative_extraction",
    ) == ("narrative-structure", "structure")
    assert narrative_section_candidates(
        question_id="story.ending", evidence_class="source_fact",
    ) == ()
    assert narrative_section_candidates(
        question_id="craft.production", evidence_class="narrative_extraction",
    ) == ("production",)
    assert narrative_section_candidates(
        question_id="reception.legacy", evidence_class="narrative_extraction",
    ) == ("reception", "reception-and-legacy", "legacy", "legacy-and-influence")
