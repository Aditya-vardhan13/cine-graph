from datetime import date

from app.services.pilot_metadata_audit import (
    classify_release_profile_date,
    classify_runtime_profile,
)


def test_release_classification_distinguishes_earliest_and_later_territory_events():
    events = [
        {"year": 2008, "date": "2008-07-18"},
        {"year": 2022, "date": "2022-10-06", "place_ids": ["Q851"]},
    ]
    assert classify_release_profile_date(date(2008, 7, 18), events, 2008, "2008-07-18") == "matches_earliest_recorded_event"
    assert classify_release_profile_date(date(2022, 10, 6), events, 2008, "2008-07-18") == "matches_other_recorded_event"


def test_release_classification_does_not_invent_exact_day_for_year_precision():
    events = [{"year": 2008, "date": None, "precision": 9}]
    assert classify_release_profile_date(date(2008, 7, 18), events, 2008, None) == "same_year_no_exact_event_match"
    assert classify_release_profile_date(None, events, 2008, None) == "legacy_date_missing"


def test_release_classification_keeps_unmatched_legacy_dates_explicit():
    events = [{"year": 2008, "date": "2008-07-18"}]
    assert classify_release_profile_date(date(2010, 1, 1), events, 2008, "2008-07-18") == "year_conflict_with_eligible_events"
    assert classify_release_profile_date(date(2008, 7, 18), [], None, None) == "no_eligible_release_event"


def test_runtime_classification_separates_missing_projection_from_source_gaps():
    assert classify_runtime_profile(None, 152, (), {"open"}) == "eligible_runtime_missing_from_legacy_profile"
    assert classify_runtime_profile(152, 152, (), {"open"}) == "matches_eligible_runtime"
    assert classify_runtime_profile(152, 164, (), {"open"}) == "runtime_value_conflict"
    assert classify_runtime_profile(None, None, (), {"local_noncommercial_only"}) == "runtime_sources_not_default_display_eligible"
    assert classify_runtime_profile(None, None, (), {None}) == "runtime_source_rights_unclassified"
    assert classify_runtime_profile(None, None, (), set()) == "no_runtime_value_found"


def test_runtime_classification_surfaces_eligible_ambiguity():
    assert classify_runtime_profile(
        None, None, ("runtime_requires_version_or_value_resolution",), {"open"},
    ) == "eligible_runtime_assertions_need_resolution"
