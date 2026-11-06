"""Pure eligibility rules for displaying source-derived structured metadata."""

DISPLAYABLE_RIGHTS_STATUSES = frozenset({
    "open",
    "attributed_reuse",
    "attribution_required",
})
LOCAL_NONCOMMERCIAL_STATUS = "local_noncommercial_only"

# Semantic retrieval, embedding and model-input use is deliberately separate
# from displaying a source-linked metadata assertion.  CC BY-SA article prose
# is reusable subject to attribution/share-alike obligations, but this app has
# not completed the product-specific review for indexing, excerpting and
# downstream model use.  A per-asset explicit approval is required before a
# narrative source can enter those paths.
NARRATIVE_SEMANTIC_USE_STATUSES = frozenset({"semantic_use_approved"})


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


def can_use_narrative_semantically(*, rights_status: str) -> bool:
    """Require explicit per-source approval before embedding/retrieval use."""
    return rights_status in NARRATIVE_SEMANTIC_USE_STATUSES
