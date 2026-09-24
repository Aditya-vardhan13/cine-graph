from app.services.hybrid_evidence_retrieval import HybridRetrievedEvidence
from app.services.story_comparison import COMPARISON_LENSES, _first_unique
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
