"""Pure classifications for the frozen pilot's legacy metadata audit."""
from __future__ import annotations

from datetime import date
from typing import Any


def classify_release_profile_date(
    legacy_date: date | None,
    release_events: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    earliest_recorded_year: int | None,
    earliest_recorded_date: str | None,
) -> str:
    """Compare a legacy profile date without mistaking territory events for errors."""
    if legacy_date is None:
        return "legacy_date_missing"
    if not release_events:
        return "no_eligible_release_event"
    exact_event_dates = {event.get("date") for event in release_events if event.get("date")}
    if legacy_date.isoformat() in exact_event_dates:
        if earliest_recorded_date == legacy_date.isoformat():
            return "matches_earliest_recorded_event"
        if earliest_recorded_date is None and earliest_recorded_year == legacy_date.year:
            return "matches_event_earliest_order_unknown"
        return "matches_other_recorded_event"
    if earliest_recorded_year == legacy_date.year:
        return "same_year_no_exact_event_match"
    return "year_conflict_with_eligible_events"


def classify_runtime_profile(
    legacy_minutes: int | None,
    eligible_minutes: int | None,
    metadata_issues: tuple[str, ...] | list[str],
    source_rights_statuses: set[str | None] | frozenset[str | None],
) -> str:
    """Separate projection gaps, real conflicts, and rights-filtered values."""
    if legacy_minutes is not None and eligible_minutes is not None:
        return "matches_eligible_runtime" if legacy_minutes == eligible_minutes else "runtime_value_conflict"
    if eligible_minutes is not None:
        return "eligible_runtime_missing_from_legacy_profile"
    if "runtime_requires_version_or_value_resolution" in metadata_issues:
        return "eligible_runtime_assertions_need_resolution"
    if legacy_minutes is not None:
        return "legacy_runtime_without_eligible_research_value"
    if None in source_rights_statuses:
        return "runtime_source_rights_unclassified"
    if source_rights_statuses and not source_rights_statuses.intersection(
        {"open", "attributed_reuse", "attribution_required"}
    ):
        return "runtime_sources_not_default_display_eligible"
    return "no_runtime_value_found"
