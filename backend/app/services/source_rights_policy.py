"""Pure eligibility rules for displaying source-derived structured metadata."""

DISPLAYABLE_RIGHTS_STATUSES = frozenset({
    "open",
    "attributed_reuse",
    "attribution_required",
    # Legacy source-wide label: tolerated for old source metadata display only.
    # It is never consulted for semantic/model-use eligibility anymore.
    "semantic_use_approved",
})
LOCAL_NONCOMMERCIAL_STATUS = "local_noncommercial_only"

# Semantic retrieval, embedding and model-input use is deliberately separate
# from displaying a source-linked metadata assertion. Eligibility requires a
# versioned decision for the specific immutable snapshot and purpose; source-
# wide metadata cannot authorize every current and future asset at once.
NARRATIVE_USE_DECISIONS = frozenset({"approved"})
NARRATIVE_SEMANTIC_LICENSES = frozenset({"CC BY-SA 4.0"})


def displayable_rights_statuses(*, include_noncommercial: bool = False) -> tuple[str, ...]:
    """Return rights states permitted in the requested local display mode.

    Link-only and unresolved states are deliberately not included. The caller
    must still display required attribution and must not infer redistribution
    rights from this eligibility check.
    """
    statuses = set(DISPLAYABLE_RIGHTS_STATUSES)
    if include_noncommercial:
        statuses.add(LOCAL_NONCOMMERCIAL_STATUS)
    return tuple(sorted(statuses))


def can_display_source(*, rights_status: str, include_noncommercial: bool = False) -> bool:
    """Pure counterpart to the SQL filter, useful for policy tests/review code."""
    return rights_status in displayable_rights_statuses(include_noncommercial=include_noncommercial)


def can_use_narrative_semantically(
    *, decision: str | None, basis_url: str | None, notes: str | None,
) -> bool:
    """Require an explicit, auditable latest per-snapshot purpose approval."""
    return bool(
        decision in NARRATIVE_USE_DECISIONS
        and basis_url and basis_url.strip()
        and notes and len(notes.strip()) >= 8
    )
