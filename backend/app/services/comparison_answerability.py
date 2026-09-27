"""Pure source-capability checks before a writer comparison retrieves passages.

These checks identify evidence types the current film-article corpus cannot
substantiate. They do not infer truth from an embedding score or declare that
all other questions have been answered.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.hybrid_evidence_retrieval import lexical_tsquery


@dataclass(frozen=True)
class SourceRequirement:
    code: str
    explanation: str


_QUANTIFIED = re.compile(r"\b(percent(?:age)?|proportion|fraction|share|how many)\b", re.I)
_AUDIENCE = re.compile(r"\b(viewers?|audiences?|moviegoers?|spectators?)\b", re.I)
_BEHAVIOR = re.compile(
    r"\b(chang(?:e|ed|ing)|affect(?:ed)?|influenc(?:e|ed)|behavio[u]?r|real.world|after seeing)\b", re.I,
)
_PRIVATE = re.compile(r"\b(private|unrecorded|off.the.record|undocumented)\b", re.I)
_EXCHANGE = re.compile(r"\b(conversation|discussion|meeting|exchange|talk)\b", re.I)
_GENERIC_QUESTION_TERMS = frozenset({
    "both", "compare", "comparison", "different", "differently", "differ", "each",
    "film", "films", "first", "movie", "movies", "second", "similar", "similarly",
    "story", "stories", "these", "those", "two", "versus",
})


def substantive_question_terms(question: str, *film_titles: str) -> tuple[str, ...]:
    """Remove prompt boilerplate and selected titles before a direct-source check."""
    title_terms = {
        token for title in film_titles
        for token in re.findall(r"[a-z0-9]+", title.casefold())
    }
    return tuple(
        token for token in lexical_tsquery(question).split(" | ")
        if token not in _GENERIC_QUESTION_TERMS | title_terms | {"cinegraph"}
    )


def unmet_source_requirement(question: str) -> SourceRequirement | None:
    """Abstain only when the requested *kind* of source is absent by design."""
    if _QUANTIFIED.search(question) and _AUDIENCE.search(question) and _BEHAVIOR.search(question):
        return SourceRequirement(
            "audience_outcome_study",
            "A measured audience-behavior study is needed. Film articles and review aggregates cannot establish "
            "how many viewers changed their real-world behavior.",
        )
    if _PRIVATE.search(question) and _EXCHANGE.search(question):
        return SourceRequirement(
            "private_primary_record",
            "A recorded interview, transcript, or other direct account is needed to establish a private production "
            "conversation. The current film-article corpus cannot verify it.",
        )
    return None
