from types import SimpleNamespace
from uuid import uuid4

from scripts.catalog_readiness_report import _narrative_use_coverage


def test_readiness_counts_only_latest_explicit_approved_attributed_open_snapshots():
    unreviewed, denied, approved, restricted = [uuid4() for _ in range(4)]
    snapshots = [
        (unreviewed, "CC BY-SA 4.0", "https://en.wikipedia.org/wiki/Film"),
        (denied, "CC BY-SA 4.0", "https://en.wikipedia.org/wiki/Film"),
        (approved, "CC BY-SA 4.0", "https://en.wikipedia.org/wiki/Film"),
        (restricted, "IMDb non-commercial", "https://example.org/film"),
    ]
    decisions = {
        denied: SimpleNamespace(decision="denied", decision_basis_url=None, decision_notes="Not approved"),
        approved: SimpleNamespace(
            decision="approved", decision_basis_url="https://creativecommons.org/licenses/by-sa/4.0/",
            decision_notes="Explicit source-specific semantic-use review.",
        ),
        restricted: SimpleNamespace(
            decision="approved", decision_basis_url="https://example.org/terms",
            decision_notes="Explicit source-specific semantic-use review.",
        ),
    }

    counts, eligible_ids = _narrative_use_coverage(snapshots, decisions)

    assert counts == {
        "total": 4,
        "with_license_and_attribution": 4,
        "with_decision": 3,
        "approved": 2,
        "denied": 1,
        "review_required": 0,
        "eligible": 1,
    }
    assert eligible_ids == {approved}
