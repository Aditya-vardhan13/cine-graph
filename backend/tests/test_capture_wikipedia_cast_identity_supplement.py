import hashlib
import json
from pathlib import Path

import pytest

from scripts.capture_wikipedia_cast_identity_supplement import (
    TARGET_SCHEMA,
    _person_capture_record,
    _reuse_snapshot,
    validate_targets,
)


def test_identity_capture_targets_require_exact_candidate_hash_and_unique_qids():
    report = {
        "schema": "cinegraph.wikipedia-cast-candidates/v8",
        "selection_sha256": "a" * 64,
        "candidates": [{
            "actor_label_in_source": "Actor Name",
            "identity_resolution": "unresolved_source_name",
        }],
    }
    report_bytes = b'{"schema":"cinegraph.wikipedia-cast-candidates/v8"}'
    targets = {
        "schema": TARGET_SCHEMA,
        "candidate_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "selection_sha256": "a" * 64,
        "targets": [{"qid": "Q21", "actor_name": "Actor Name"}],
    }

    assert validate_targets(report, report_bytes, targets) == [{"qid": "Q21", "actor_name": "Actor Name"}]


def test_identity_capture_targets_reject_candidate_report_substitution():
    report = {
        "schema": "cinegraph.wikipedia-cast-candidates/v8",
        "selection_sha256": "a" * 64,
        "candidates": [{
            "actor_label_in_source": "Actor Name",
            "identity_resolution": "unresolved_source_name",
        }],
    }
    targets = {
        "schema": TARGET_SCHEMA,
        "candidate_report_sha256": "b" * 64,
        "selection_sha256": "a" * 64,
        "targets": [{"qid": "Q21", "actor_name": "Actor Name"}],
    }

    with pytest.raises(ValueError, match="bound to another"):
        validate_targets(report, b"candidate report", targets)


def test_identity_capture_targets_reject_duplicate_or_invalid_qids():
    report = {
        "schema": "cinegraph.wikipedia-cast-candidates/v8",
        "selection_sha256": "a" * 64,
        "candidates": [{
            "actor_label_in_source": "Actor Name",
            "identity_resolution": "unresolved_source_name",
        }],
    }
    report_bytes = b"candidate report"
    for values in (
        [{"qid": "Q21", "actor_name": "Actor Name"}, {"qid": "Q21", "actor_name": "Actor Name"}],
        [{"qid": "21", "actor_name": "Actor Name"}],
    ):
        targets = {
            "schema": TARGET_SCHEMA,
            "candidate_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "selection_sha256": "a" * 64,
            "targets": values,
        }
        with pytest.raises(ValueError, match="valid QID|duplicate"):
            validate_targets(report, report_bytes, targets)


def test_retained_person_snapshot_is_verified_as_human_and_exact_candidate_alias(tmp_path: Path):
    payload = json.dumps({"entities": {"Q21": {
        "id": "Q21", "lastrevid": 123,
        "labels": {"en": {"value": "Stage Name"}},
        "aliases": {"en": [{"value": "Actor Name"}]},
        "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]},
    }}}).encode()
    digest = hashlib.sha256(payload).hexdigest()
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    path = snapshot_dir / f"Q21-{digest}.json"
    path.write_bytes(payload)

    record = _reuse_snapshot(tmp_path, "Q21", "Actor Name")

    assert record == {
        "english_label": "Stage Name",
        "source_url": "https://www.wikidata.org/wiki/Special:EntityData/Q21.json",
        "source_revision": 123,
        "sha256": digest,
        "license": "CC0 1.0",
        "snapshot_path": f"snapshots/Q21-{digest}.json",
    }


def test_retained_snapshot_rejects_wrong_person_type_or_name(tmp_path: Path):
    payload = json.dumps({"entities": {"Q21": {
        "id": "Q21", "lastrevid": 123,
        "labels": {"en": {"value": "Not the actor"}},
        "claims": {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}]},
    }}}).encode()
    digest = hashlib.sha256(payload).hexdigest()
    snapshot_dir = tmp_path / "snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / f"Q21-{digest}.json").write_bytes(payload)

    with pytest.raises(ValueError, match="not explicitly typed as a human"):
        _person_capture_record("Q21", "Actor Name", payload, f"snapshots/Q21-{digest}.json")
