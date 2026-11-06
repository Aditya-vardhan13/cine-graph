from pathlib import Path
import math

import pytest

from app.services.english_pilot_raw_replay import (
    EnglishPilotReplayError,
    _capture_path,
    _validate_capture_manifest_shape,
    _validate_capture_policy,
    _validate_pilot_shape,
)
from app.services.wikidata_raw import RawWikidataError, validate_capture_hashes
from app.services.wikipedia_raw import RawWikipediaError, validate_article_capture_hashes


def test_capture_policy_requires_sequential_robots_checked_entitydata() -> None:
    _validate_capture_policy({
        "concurrency": 1,
        "minimum_interval_seconds": 1.0,
        "robots_required": True,
        "stop_on_denial_or_rate_limit": True,
        "wikidata_route": "known-QID Special:EntityData JSON only",
        "wikipedia_route": "known enwiki sitelink ordinary /wiki/ page only",
    }, batch_name="fixture")


@pytest.mark.parametrize("change", [
    {"concurrency": 2},
    {"concurrency": True},
    {"minimum_interval_seconds": 0.5},
    {"minimum_interval_seconds": math.nan},
    {"minimum_interval_seconds": math.inf},
    {"minimum_interval_seconds": True},
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
        "wikipedia_route": "known enwiki sitelink ordinary /wiki/ page only",
    }
    policy.update(change)
    with pytest.raises(EnglishPilotReplayError, match="less restrictive"):
        _validate_capture_policy(policy, batch_name="fixture")


def test_frozen_pilot_shape_requires_unique_rows_with_explicit_ids() -> None:
    rows = [{"selection_rank": rank, "catalog_film_id": f"film-{rank}", "wikidata_id": f"Q{rank}"}
            for rank in range(1, 101)]
    assert _validate_pilot_shape({"films": rows}) == rows
    malformed = [{"selection_rank": rank, "catalog_film_id": f"film-{rank}", "wikidata_id": f"Q{rank}"}
                 for rank in range(1, 100)] + [None]
    with pytest.raises(EnglishPilotReplayError, match="malformed film row"):
        _validate_pilot_shape({"films": malformed})
    with pytest.raises(EnglishPilotReplayError, match="unique and contiguous"):
        _validate_pilot_shape({"films": [*rows[:-1], {**rows[-1], "selection_rank": 99}]})


def test_capture_manifest_shape_rejects_unstructured_json() -> None:
    valid = {"schema": "cinegraph.catalog-pilot-capture/v1", "films": [{"qid": "Q1"}]}
    _validate_capture_manifest_shape(valid, batch_name="fixture")
    for malformed in ([], {"schema": "wrong", "films": []},
                      {"schema": "cinegraph.catalog-pilot-capture/v1", "films": [None]}):
        with pytest.raises(EnglishPilotReplayError, match="invalid structure"):
            _validate_capture_manifest_shape(malformed, batch_name="fixture")


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
    validate_article_capture_hashes(robots_sha256="c" * 64, manifest_sha256="d" * 64)
    with pytest.raises(RawWikipediaError, match="robots.txt SHA-256"):
        validate_article_capture_hashes(robots_sha256="missing", manifest_sha256="d" * 64)
