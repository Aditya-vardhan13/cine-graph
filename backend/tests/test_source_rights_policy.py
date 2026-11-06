import pytest

from app.services.source_rights_policy import (
    NARRATIVE_SEMANTIC_LICENSES, can_display_source, can_use_narrative_semantically,
    displayable_rights_statuses,
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
        "semantic_use_approved",
    )


def test_semantic_use_requires_explicit_snapshot_decision_separate_from_display_rights():
    assert can_display_source(rights_status="attributed_reuse")
    approved_fields = {
        "decision": "approved", "basis_url": "https://example.test/policy",
        "notes": "Reviewed intended use.", "license_name": "CC BY-SA 4.0",
        "attribution_url": "https://example.test/source",
    }
    assert not can_use_narrative_semantically(
        decision=None, basis_url=None, notes=None, license_name="CC BY-SA 4.0",
        attribution_url="https://example.test/source",
    )
    assert not can_use_narrative_semantically(
        **(approved_fields | {"decision": "review_required"}),
    )
    assert not can_use_narrative_semantically(
        **(approved_fields | {"decision": "denied"}),
    )
    assert not can_use_narrative_semantically(
        **(approved_fields | {"basis_url": None}),
    )
    assert not can_use_narrative_semantically(
        **(approved_fields | {"notes": "short"}),
    )
    assert not can_use_narrative_semantically(
        **(approved_fields | {"license_name": "CC BY-NC 4.0"}),
    )
    assert not can_use_narrative_semantically(**(approved_fields | {"attribution_url": None}))
    assert not can_use_narrative_semantically(**(approved_fields | {"attribution_url": "http://example.test/source"}))
    assert not can_use_narrative_semantically(**(approved_fields | {"basis_url": "https:///missing-host"}))
    assert can_use_narrative_semantically(**approved_fields)


def test_narrative_semantic_license_allowlist_is_shared_and_explicit():
    assert NARRATIVE_SEMANTIC_LICENSES == frozenset({"CC BY-SA 4.0"})
