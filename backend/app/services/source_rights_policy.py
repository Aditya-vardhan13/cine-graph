"""Pure eligibility rules for displaying source-derived structured metadata."""

DISPLAYABLE_RIGHTS_STATUSES = frozenset({
    "open",
    "attributed_reuse",
    "attribution_required",
})
LOCAL_NONCOMMERCIAL_STATUS = "local_noncommercial_only"


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
