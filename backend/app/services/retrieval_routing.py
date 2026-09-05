"""Pure policy for selecting CineGraph's evidence-retrieval lane.

This classifies the *kind of evidence requested*, never the truth of the
answer.  A semantic ranking can nominate a narrative passage, but it must not
replace the typed assertion path for an objective fact.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RetrievalLane(StrEnum):
    STRUCTURED = "structured"
    LEXICAL = "lexical"
    NARRATIVE_SEMANTIC = "narrative_semantic"
    CRITICAL_INTERPRETATION = "critical_interpretation"


@dataclass(frozen=True)
class RetrievalRoute:
    """A route and its permitted fallback candidates, in preference order."""

    primary: RetrievalLane
    candidates: tuple[RetrievalLane, ...]
    reason: str


_STRUCTURED_PREFIXES = (
    "identity.", "release.", "credit.", "lineage.", "award.", "company.",
)
_NARRATIVE_PREFIXES = (
    "story.", "character.", "structure.", "premise.", "craft.",
)
_INTERPRETATION_PREFIXES = ("theme.", "impact.", "reading.", "interpretation.")


def route_research_question(*, question_id: str, evidence_class: str | None = None) -> RetrievalRoute:
    """Choose evidence sources without inspecting model scores or database state.

    ``evidence_class`` comes from a reviewed research-question definition when
    it is available. ``question_id`` provides the stable fallback for catalog
    questions that have not been materialised yet.
    """
    normalized_id = question_id.casefold().strip()
    normalized_class = (evidence_class or "").casefold().strip()

    if normalized_class == "source_fact" or normalized_id.startswith(_STRUCTURED_PREFIXES):
        return RetrievalRoute(
            primary=RetrievalLane.STRUCTURED,
            candidates=(RetrievalLane.STRUCTURED, RetrievalLane.LEXICAL),
            reason="objective facts require asserted, source-linked statements",
        )
    if normalized_class in {"attributed_interpretation", "editorial_interpretation"} or normalized_id.startswith(_INTERPRETATION_PREFIXES):
        return RetrievalRoute(
            primary=RetrievalLane.CRITICAL_INTERPRETATION,
            candidates=(RetrievalLane.CRITICAL_INTERPRETATION, RetrievalLane.NARRATIVE_SEMANTIC),
            reason="interpretive questions need an attributed criticism corpus",
        )
    if normalized_class == "narrative_extraction" or normalized_id.startswith(_NARRATIVE_PREFIXES):
        return RetrievalRoute(
            primary=RetrievalLane.NARRATIVE_SEMANTIC,
            candidates=(RetrievalLane.NARRATIVE_SEMANTIC, RetrievalLane.LEXICAL),
            reason="narrative passages are semantic candidates with lexical fallback",
        )
    return RetrievalRoute(
        primary=RetrievalLane.LEXICAL,
        candidates=(RetrievalLane.LEXICAL, RetrievalLane.STRUCTURED, RetrievalLane.NARRATIVE_SEMANTIC),
        reason="unclassified research starts with attributable exact-term evidence",
    )


def narrative_section_candidates(*, question_id: str, evidence_class: str | None = None) -> tuple[str, ...]:
    """Return a declared section prior without inspecting retrieval scores."""
    if (evidence_class or "").casefold().strip() != "narrative_extraction":
        return ()
    normalized_id = question_id.casefold().strip()
    if normalized_id.startswith("story."):
        return ("plot",)
    if normalized_id.startswith("structure."):
        return ("narrative-structure", "structure")
    return ()
