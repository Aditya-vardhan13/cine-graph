import pytest

from app.services.source_rights_policy import (
    can_display_source, can_use_narrative_semantically, displayable_rights_statuses,
)


@pytest.mark.parametrize("status", ["open", "attributed_reuse", "attribution_required"])
def test_explicitly_eligible_rights_states_are_displayable(status):
    assert can_display_source(rights_status=status)


@pytest.mark.parametrize("status", ["metadata_link_only", "review_required", "unknown", ""])
def test_link_only_and_unresolved_rights_are_not_displayable(status):
    assert not can_display_source(rights_status=status)
    assert not can_display_source(rights_status=status, include_noncommercial=True)


def test_noncommercial_metadata_requires_explicit_local_opt_in():
    assert not can_display_source(rights_status="local_noncommercial_only")
    assert can_display_source(rights_status="local_noncommercial_only", include_noncommercial=True)
    assert displayable_rights_statuses(include_noncommercial=True) == (
        "attributed_reuse", "attribution_required", "local_noncommercial_only", "open",
    )


def test_semantic_use_requires_explicit_source_approval_separate_from_display_rights():
    assert can_display_source(rights_status="attributed_reuse")
    assert not can_use_narrative_semantically(rights_status="attributed_reuse")
    assert not can_use_narrative_semantically(rights_status="local_noncommercial_only")
    assert not can_use_narrative_semantically(rights_status="review_required")
    assert can_use_narrative_semantically(rights_status="semantic_use_approved")
