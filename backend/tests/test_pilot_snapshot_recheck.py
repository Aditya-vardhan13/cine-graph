from hashlib import sha256

import pytest

from app.services.pilot_snapshot_recheck import (
    PilotSnapshotRecheckError,
    recheck_unmapped_pilot_snapshots,
)
from scripts.recheck_pilot_snapshot_integrity import local_evaluation_path


def _audit(snapshot_path, digest, size):
    evidence = {
        "snapshot_id": "snapshot-1",
        "snapshot_storage_uri": snapshot_path.as_uri(),
        "snapshot_hash": digest,
        "snapshot_byte_size": size,
        "snapshot_integrity_status": "unmapped",
    }
    return {
        "version": "pilot-metadata-projection-audit-v4",
        "film_count": 1,
        "films": [{
            "input_title": "Example Film",
            "wikidata_id": "Q123",
            "source_assertions": {"runtimes": [{"source_evidence": [evidence]}]},
        }],
    }


def test_rechecks_local_unmapped_snapshot_against_exact_hash_and_size(tmp_path):
    payload = b"retained source bytes"
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(payload)
    report = recheck_unmapped_pilot_snapshots(
        _audit(snapshot, sha256(payload).hexdigest(), len(payload)),
        audit_sha256="a" * 64,
    )

    assert report["local_recheck_status_counts"] == {"verified": 1}
    assert report["snapshots"][0]["local_recheck_status"] == "verified"
    assert report["snapshots"][0]["film_title"] == "Example Film"


@pytest.mark.parametrize("expected_hash,expected_size", [
    ("0" * 64, len(b"retained source bytes")),
    (sha256(b"retained source bytes").hexdigest(), len(b"retained source bytes") + 1),
])
def test_recheck_never_calls_a_changed_or_wrong_sized_file_verified(tmp_path, expected_hash, expected_size):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(b"retained source bytes")
    report = recheck_unmapped_pilot_snapshots(
        _audit(snapshot, expected_hash, expected_size), audit_sha256="a" * 64,
    )

    expected_status = "hash_mismatch" if expected_hash == "0" * 64 else "size_mismatch"
    assert report["local_recheck_status_counts"] == {expected_status: 1}


def test_recheck_deduplicates_repeated_snapshot_references(tmp_path):
    payload = b"same bytes"
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(payload)
    audit = _audit(snapshot, sha256(payload).hexdigest(), len(payload))
    audit["films"][0]["source_assertions"]["release_events"] = audit["films"][0]["source_assertions"]["runtimes"]

    report = recheck_unmapped_pilot_snapshots(audit, audit_sha256="a" * 64)

    assert report["previously_unmapped_snapshot_count"] == 1


def test_recheck_rejects_conflicting_descriptions_for_same_snapshot(tmp_path):
    payload = b"same bytes"
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(payload)
    audit = _audit(snapshot, sha256(payload).hexdigest(), len(payload))
    second = dict(audit["films"][0]["source_assertions"]["runtimes"][0]["source_evidence"][0])
    second["snapshot_hash"] = "0" * 64
    audit["films"][0]["source_assertions"]["release_events"] = [{"source_evidence": [second]}]

    with pytest.raises(PilotSnapshotRecheckError, match="inconsistent"):
        recheck_unmapped_pilot_snapshots(audit, audit_sha256="a" * 64)


def test_recheck_requires_exact_input_fingerprint(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_bytes(b"x")
    with pytest.raises(PilotSnapshotRecheckError, match="SHA-256"):
        recheck_unmapped_pilot_snapshots(_audit(snapshot, sha256(b"x").hexdigest(), 1), audit_sha256="bad")


def test_report_paths_are_confined_to_evaluation_root(tmp_path):
    root = tmp_path / "data" / "evaluation"
    assert local_evaluation_path(root / "report.json", root) == (root / "report.json").resolve()
    with pytest.raises(ValueError, match="stay under"):
        local_evaluation_path(tmp_path / "outside.json", root)
