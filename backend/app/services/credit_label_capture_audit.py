"""Offline integrity and coverage audit for retained Wikidata credit labels."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from app.services.credit_target_manifest import QID
from app.services.wikidata_raw import entity_from_entitydata

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ROBOTS_SHA256 = SHA256


def audit_credit_label_capture(manifest_path: Path, capture_dir: Path) -> dict[str, Any]:
    """Require a complete, manifest-bound capture and report label coverage.

    The checkpoint cannot redefine its own target set: its digest must match
    the immutable manifest bytes. Each response is then checked for content
    hash, requested entity ID, revision, allowed source URL, robots digest and
    exact English-label agreement before it counts as retained evidence.
    """
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != "cinegraph.credit-target-manifest/v1":
        raise ValueError("Unexpected credit-target manifest schema")
    targets = manifest.get("targets")
    if not isinstance(targets, list):
        raise ValueError("Credit-target manifest has no targets list")
    by_qid = {target.get("qid"): target for target in targets if isinstance(target, dict)}
    if len(by_qid) != len(targets) or any(not isinstance(qid, str) or not QID.fullmatch(qid) for qid in by_qid):
        raise ValueError("Credit-target manifest contains invalid or duplicate QIDs")

    checkpoint_path = capture_dir / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    expected_manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    if checkpoint.get("manifest_sha256") != expected_manifest_hash:
        raise ValueError("Capture checkpoint does not belong to this target manifest")
    captured = checkpoint.get("captured")
    if not isinstance(captured, dict) or set(captured) != set(by_qid):
        raise ValueError("Credit-label capture is incomplete or contains unknown targets")

    robots_hashes: set[str] = set()
    label_qids: set[str] = set()
    total_bytes = 0
    for qid, row in captured.items():
        if not isinstance(row, dict) or not isinstance(row.get("sha256"), str) or not SHA256.fullmatch(row["sha256"]):
            raise ValueError(f"Invalid capture metadata for {qid}")
        expected_relative = Path("snapshots") / qid / f"{row['sha256']}.json"
        if row.get("snapshot_path") != expected_relative.as_posix():
            raise ValueError(f"Unexpected snapshot path for {qid}")
        payload = (capture_dir / expected_relative).read_bytes()
        if hashlib.sha256(payload).hexdigest() != row["sha256"]:
            raise ValueError(f"Snapshot hash mismatch for {qid}")
        entity = entity_from_entitydata(json.loads(payload), qid)
        if str(entity.get("lastrevid")) != str(row.get("source_revision")):
            raise ValueError(f"Source revision mismatch for {qid}")
        source_url = row.get("source_url", "")
        if not re.fullmatch(r"https://www\.wikidata\.org/wiki/Special:EntityData/Q[1-9]\d*\.json", source_url):
            raise ValueError(f"Unapproved source URL for {qid}")
        if source_url.rsplit("/", 1)[-1] != f"{qid}.json":
            raise ValueError(f"Source URL does not match requested QID {qid}")
        robots_hash = row.get("robots_sha256")
        if not isinstance(robots_hash, str) or not ROBOTS_SHA256.fullmatch(robots_hash):
            raise ValueError(f"Invalid robots.txt digest for {qid}")
        robots_hashes.add(robots_hash)
        label_value = entity.get("labels", {}).get("en", {}).get("value")
        if label_value != row.get("english_label"):
            raise ValueError(f"English label mismatch for {qid}")
        if isinstance(label_value, str) and label_value.strip():
            label_qids.add(qid)
        total_bytes += len(payload)

    films: dict[str, dict[str, int]] = {}
    role_references: dict[str, int] = {}
    named_cast: set[str] = set()
    named_character_cast: set[str] = set()
    for qid, target in by_qid.items():
        for reference in target.get("references", []):
            film_qid = reference.get("film_qid")
            role = reference.get("role")
            if not isinstance(film_qid, str) or not QID.fullmatch(film_qid):
                raise ValueError(f"Invalid film reference for credit target {qid}")
            if role not in {"cast", "character", "director", "writer"}:
                raise ValueError(f"Invalid role reference for credit target {qid}")
            role_references[role] = role_references.get(role, 0) + 1
            film = films.setdefault(film_qid, {"references": 0, "targets": 0})
            film["references"] += 1
            film["targets"] += 1
            if role == "cast" and qid in label_qids:
                named_cast.add(film_qid)
            if role == "character" and qid in label_qids and reference.get("person_qid") in label_qids:
                named_character_cast.add(film_qid)
    return {
        "schema": "cinegraph.credit-label-capture-audit/v1",
        "manifest_sha256": expected_manifest_hash,
        "films": len(films),
        "targets": len(by_qid),
        "captured": len(captured),
        "with_english_label": len(label_qids),
        "without_english_label": len(by_qid) - len(label_qids),
        "role_references": dict(sorted(role_references.items())),
        "films_with_named_cast": len(named_cast),
        "films_with_named_character_candidates": len(named_character_cast),
        "robots_sha256_count": len(robots_hashes),
        "snapshot_bytes": total_bytes,
        "status": "complete",
    }
