from app.services.hybrid_evidence_retrieval import HybridRetrievedEvidence
from app.services.story_comparison import COMPARISON_LENSES, _first_unique, focus_evidence_question_id
from app.services.comparison_answerability import substantive_question_terms, unmet_source_requirement
from app.services.research_catalog import display_film_title


def evidence(identifier: str) -> HybridRetrievedEvidence:
    return HybridRetrievedEvidence(
        chunk_id=identifier,
        subject_entity_id="subject",
        source_snapshot_id="snapshot",
        section_locator="plot",
        section_title="Plot",
        content=f"Attributable {identifier} fixture passage.",
        rank=1,
        fused_score=None,
        semantic_similarity=None,
        lexical_score=1.0,
        matched_by=("lexical",),
    )


def test_comparison_lenses_cover_story_character_craft_and_reception() -> None:
    identifiers = [lens.identifier for lens in COMPARISON_LENSES]
    assert identifiers == [
        "central_question",
        "story_engine",
        "character_change",
        "craft_treatment",
        "reception_legacy",
    ]
    assert all("artificial companion" in lens.query("artificial companion") for lens in COMPARISON_LENSES)
    assert all(lens.writer_prompt for lens in COMPARISON_LENSES)


def test_writer_focus_routes_by_requested_evidence_kind_without_film_topic_rules() -> None:
    assert focus_evidence_question_id("How does gaining power change family loyalty?") == "story.writer_focus"
    assert focus_evidence_question_id("Which practical effects and camera choices make the monster present?") == "craft.writer_focus"
    assert focus_evidence_question_id("How did editing and music make a chaotic chase readable?") == "craft.writer_focus"
    assert focus_evidence_question_id("Where do critics disagree about the ending?") == "reception.writer_focus"
    assert focus_evidence_question_id("How did reviewers assess its visual effects?") == "reception.writer_focus"


def test_first_unique_never_fills_a_sparse_lens_with_repeated_text() -> None:
    first = evidence("first")
    second = evidence("second")
    used = {first.content.casefold()}

    assert _first_unique((first, second), used) == second
    assert used == {first.content.casefold(), second.content.casefold()}
    assert _first_unique((first,), used) is None
    assert _first_unique((), used) is None


def test_different_chunk_ids_with_equivalent_content_are_not_distinct_evidence() -> None:
    from dataclasses import replace
    first = evidence("first")
    duplicate = replace(first, chunk_id="different-id", content=first.content.upper() + "\n")
    used = set()
    assert _first_unique((first,), used) == first
    assert _first_unique((duplicate,), used) is None


def test_research_title_removes_only_mediawiki_film_disambiguation() -> None:
    assert display_film_title("Her (2013 film)") == "Her"
    assert display_film_title("Blade Runner 2049") == "Blade Runner 2049"
    assert display_film_title("Brazil (1985)") == "Brazil (1985)"


def test_source_capability_abstains_on_unavailable_evidence_types() -> None:
    assert unmet_source_requirement(
        "What percentage of audience members changed their behavior after seeing these films?"
    ).code == "audience_outcome_study"
    assert unmet_source_requirement(
        "Which private meeting between the editors caused the ending to change?"
    ).code == "private_primary_record"
    assert unmet_source_requirement(
        "How do these films put a character's moral code under pressure?"
    ) is None
    assert unmet_source_requirement(
        "How many viewers saw the film in its first weekend?"
    ) is None


def test_focus_terms_remove_comparison_boilerplate_and_selected_titles() -> None:
    assert substantive_question_terms(
        "How do Batman Begins and The Dark Knight differ in moral compromise?",
        "Batman Begins", "The Dark Knight",
    ) == ("moral", "compromise")
    assert substantive_question_terms(
        "How are these two films different?", "Batman Begins", "The Dark Knight",
    ) == ()
