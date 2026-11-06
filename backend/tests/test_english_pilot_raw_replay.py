from pathlib import Path

import pytest

from app.services.english_pilot_raw_replay import (
    EnglishPilotReplayError,
    _capture_path,
    _validate_capture_policy,
)
from app.services.wikidata_raw import RawWikidataError, validate_capture_hashes


def test_capture_policy_requires_sequential_robots_checked_entitydata() -> None:
    _validate_capture_policy({
        "concurrency": 1,
        "minimum_interval_seconds": 1.0,
        "robots_required": True,
        "stop_on_denial_or_rate_limit": True,
        "wikidata_route": "known-QID Special:EntityData JSON only",
    }, batch_name="fixture")


@pytest.mark.parametrize("change", [
    {"concurrency": 2},
    {"minimum_interval_seconds": 0.5},
    {"robots_required": False},
    {"stop_on_denial_or_rate_limit": False},
    {"wikidata_route": "query service"},
])
def test_capture_policy_rejects_unapproved_route_or_rate(change: dict[str, object]) -> None:
    policy: dict[str, object] = {
        "concurrency": 1,
        "minimum_interval_seconds": 1.0,
        "robots_required": True,
        "stop_on_denial_or_rate_limit": True,
        "wikidata_route": "known-QID Special:EntityData JSON only",
    }
    policy.update(change)
    with pytest.raises(EnglishPilotReplayError, match="less restrictive"):
        _validate_capture_policy(policy, batch_name="fixture")


def test_capture_path_resolves_only_inside_its_batch(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    (batch / "snapshots").mkdir(parents=True)
    (batch / "snapshots" / "Q1.json").write_bytes(b"{}")
    assert _capture_path(batch, "snapshots/Q1.json", qid="Q1").read_bytes() == b"{}"

    outside = tmp_path / "outside.json"
    outside.write_bytes(b"{}")
    with pytest.raises(EnglishPilotReplayError, match="escapes"):
        _capture_path(batch, "../outside.json", qid="Q1")


def test_capture_path_rejects_symlink_even_when_target_is_inside_batch(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    (batch / "snapshots").mkdir(parents=True)
    target = batch / "snapshots" / "real.json"
    target.write_bytes(b"{}")
    (batch / "snapshots" / "alias.json").symlink_to(target)

    with pytest.raises(EnglishPilotReplayError, match="symlinked"):
        _capture_path(batch, "snapshots/alias.json", qid="Q1")


def test_capture_provenance_hashes_are_validated_before_ingestion() -> None:
    validate_capture_hashes(robots_sha256="a" * 64, manifest_sha256="b" * 64)
    with pytest.raises(RawWikidataError, match="manifest SHA-256"):
        validate_capture_hashes(robots_sha256="a" * 64, manifest_sha256="nope")
