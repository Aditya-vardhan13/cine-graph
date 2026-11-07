"""Capture explicitly selected Wikidata person identities for unmatched cast names.

This is an opt-in, rate-limited source action. It reads a curator-prepared QID
target manifest, checks Wikidata robots.txt, captures EntityData sequentially,
and writes immutable local snapshots under data/evaluation. It never asserts
that a person appeared in a film.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from app.core.config import get_settings
from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikidata_raw import WikidataEntityDataFetcher
from app.services.wikipedia_cast_source_statements import IDENTITY_SUPPLEMENT_SCHEMA, INPUT_SCHEMA


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = PROJECT_ROOT / "data" / "evaluation"
TARGET_SCHEMA = "cinegraph.wikipedia-cast-identity-targets/v1"
QID = re.compile(r"^Q[1-9][0-9]*$")


def _read_local_json(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Inputs must be regular, non-symlink JSON files")
    resolved = path.resolve(strict=True)
    if EVALUATION_ROOT.resolve(strict=True) not in resolved.parents:
        raise ValueError("All capture inputs must remain inside local data/evaluation")
    raw = resolved.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Input JSON root must be an object")
    return value, raw


def validate_targets(report: dict, report_bytes: bytes, targets: dict) -> list[dict[str, str]]:
    if report.get("schema") != INPUT_SCHEMA:
        raise ValueError(f"Expected candidate report schema {INPUT_SCHEMA}")
    target_rows = targets.get("targets")
    if (targets.get("schema") != TARGET_SCHEMA
            or targets.get("candidate_report_sha256") != hashlib.sha256(report_bytes).hexdigest()
            or targets.get("selection_sha256") != report.get("selection_sha256")
            or not isinstance(target_rows, list) or not target_rows):
        raise ValueError("Identity target manifest is malformed or bound to another candidate report")
    candidate_names = {
        row.get("actor_label_in_source")
        for row in report.get("candidates", [])
        if isinstance(row, dict) and row.get("identity_resolution") == "unresolved_source_name"
    }
    validated: list[dict[str, str]] = []
    qids: set[str] = set()
    for row in target_rows:
        if not isinstance(row, dict):
            raise ValueError("Identity target rows must be objects")
        qid, actor_name = row.get("qid"), row.get("actor_name")
        if (not isinstance(qid, str) or not QID.fullmatch(qid)
                or not isinstance(actor_name, str) or not actor_name.strip()
                or actor_name not in candidate_names):
            raise ValueError("Identity target rows must bind a valid QID to an unresolved candidate name")
        if qid in qids:
            raise ValueError("Identity target manifest contains duplicate QIDs")
        qids.add(qid)
        validated.append({"qid": qid, "actor_name": actor_name})
    return validated


def _person_capture_record(qid: str, actor_name: str, payload: bytes, snapshot_path: str) -> dict:
    try:
        entity = json.loads(payload).get("entities", {}).get(qid, {})
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
        raise ValueError(f"Retained Wikidata person payload is invalid for {qid}") from exc
    if not isinstance(entity, dict) or entity.get("id") != qid:
        raise ValueError(f"Retained Wikidata entity does not match requested QID {qid}")
    revision = entity.get("lastrevid")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValueError(f"Retained Wikidata entity has no valid revision for {qid}")
    claims = entity.get("claims", {})
    instance_of = claims.get("P31", []) if isinstance(claims, dict) else []
    is_human = isinstance(instance_of, list) and any(
        claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q5"
        for claim in instance_of
        if isinstance(claim, dict)
        and isinstance(claim.get("mainsnak"), dict)
        and isinstance(claim["mainsnak"].get("datavalue"), dict)
        and isinstance(claim["mainsnak"]["datavalue"].get("value"), dict)
    )
    if not is_human:
        raise ValueError(f"Selected identity item is not explicitly typed as a human: {qid}")
    labels = entity.get("labels", {})
    label_row = labels.get("en", {}) if isinstance(labels, dict) else {}
    english_label = label_row.get("value") if isinstance(label_row, dict) else None
    if not isinstance(english_label, str) or not english_label.strip():
        raise ValueError(f"Selected Wikidata person has no English label: {qid}")
    aliases_by_language = entity.get("aliases", {})
    aliases = aliases_by_language.get("en", []) if isinstance(aliases_by_language, dict) else []
    if english_label != actor_name and not any(
        isinstance(alias, dict) and alias.get("value") == actor_name for alias in aliases
    ):
        raise ValueError(f"Wikidata identity label/alias does not match selected candidate {actor_name}: {qid}")
    return {
        "english_label": english_label,
        "source_url": f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
        "source_revision": revision,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "license": "CC0 1.0",
        "snapshot_path": snapshot_path,
    }


def _reuse_snapshot(output_dir: Path, qid: str, actor_name: str) -> dict | None:
    snapshot_dir = output_dir / "snapshots"
    if snapshot_dir.is_symlink():
        raise ValueError("Identity snapshot directory cannot be a symlink")
    if not snapshot_dir.exists():
        return None
    root = output_dir.resolve(strict=True)
    resolved_snapshot_dir = snapshot_dir.resolve(strict=True)
    if root not in resolved_snapshot_dir.parents:
        raise ValueError("Identity snapshot directory escapes output directory")
    candidates = sorted(snapshot_dir.glob(f"{qid}-*.json"))
    if not candidates:
        return None
    if len(candidates) != 1:
        raise ValueError(f"Expected at most one retained snapshot for {qid}; refusing ambiguous reuse")
    path = candidates[0]
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Retained identity snapshot must be a regular file for {qid}")
    resolved_path = path.resolve(strict=True)
    if root not in resolved_path.parents:
        raise ValueError(f"Retained identity snapshot escapes output directory for {qid}")
    payload = resolved_path.read_bytes()
    relative = path.relative_to(output_dir).as_posix()
    record = _person_capture_record(qid, actor_name, payload, relative)
    if path.name != f"{qid}-{record['sha256']}.json":
        raise ValueError(f"Retained identity snapshot filename does not match its content hash for {qid}")
    return record


def capture(report_path: Path, targets_path: Path, output_dir: Path) -> dict:
    report, report_bytes = _read_local_json(report_path)
    targets, targets_bytes = _read_local_json(targets_path)
    target_rows = validate_targets(report, report_bytes, targets)
    qids = [row["qid"] for row in target_rows]
    if output_dir.is_symlink():
        raise ValueError("Output directory cannot be a symlink")
    output_dir = output_dir.resolve()
    if EVALUATION_ROOT.resolve(strict=True) not in output_dir.parents:
        raise ValueError("Capture output must remain inside local data/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_dir = output_dir / "snapshots"
    if snapshot_dir.is_symlink():
        raise ValueError("Snapshot output directory cannot be a symlink")
    snapshot_dir.mkdir(exist_ok=True)
    manifest_path = output_dir / "identity-supplement-manifest.json"
    if manifest_path.exists():
        existing, existing_bytes = _read_local_json(manifest_path)
        if (existing.get("schema") != IDENTITY_SUPPLEMENT_SCHEMA
                or existing.get("candidate_report_sha256") != hashlib.sha256(report_bytes).hexdigest()
                or existing.get("target_manifest_sha256") != hashlib.sha256(targets_bytes).hexdigest()):
            raise ValueError("Existing identity capture belongs to different immutable inputs")
        existing_captured = existing.get("captured")
        if not isinstance(existing_captured, dict) or set(existing_captured) != set(qids):
            raise ValueError("Existing identity capture does not cover the exact target QID set")
        for qid, record in existing_captured.items():
            if not isinstance(record, dict):
                raise ValueError(f"Malformed retained identity capture record for {qid}")
            relative = Path(record["snapshot_path"])
            if relative.is_absolute() or ".." in relative.parts or relative.is_symlink():
                raise ValueError(f"Unsafe retained identity snapshot path for {qid}")
            retained = (output_dir / relative).resolve(strict=True)
            if output_dir.resolve(strict=True) not in retained.parents:
                raise ValueError(f"Retained identity snapshot escapes output directory for {qid}")
            if hashlib.sha256(retained.read_bytes()).hexdigest() != record.get("sha256"):
                raise ValueError(f"Retained identity snapshot fails its hash for {qid}")
        return {
            "manifest": str(manifest_path), "target_count": len(qids),
            "captured_count": len(existing_captured),
            "manifest_sha256": hashlib.sha256(existing_bytes).hexdigest(),
            "reused_existing_capture": True,
        }
    settings = get_settings()
    captured: dict[str, dict] = {}
    with WikidataEntityDataFetcher(
        user_agent=settings.wikidata_user_agent,
        interval_seconds=max(1.0, settings.source_request_interval_seconds),
    ) as fetcher:
        for target in target_rows:
            qid, actor_name = target["qid"], target["actor_name"]
            record = _reuse_snapshot(output_dir, qid, actor_name)
            if record is None:
                item = fetcher.fetch(qid)
                digest = hashlib.sha256(item.payload).hexdigest()
                relative_path = f"snapshots/{qid}-{digest}.json"
                _write_immutable(output_dir / relative_path, item.payload)
                record = _person_capture_record(qid, actor_name, item.payload, relative_path)
            captured[qid] = record
        manifest = {
            "schema": IDENTITY_SUPPLEMENT_SCHEMA,
            "candidate_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "selection_sha256": report["selection_sha256"],
            "target_manifest_sha256": hashlib.sha256(targets_bytes).hexdigest(),
            "target_qids": qids,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "robots_sha256": fetcher.robots_sha256,
            "captured": captured,
        }
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    _write_immutable(manifest_path, manifest_bytes)
    return {
        "manifest": str(manifest_path),
        "target_count": len(qids),
        "captured_count": len(captured),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_report", type=Path, help="Retained, unresolved v8 candidate report")
    parser.add_argument("targets", type=Path, help="Curator-prepared identity-target JSON manifest")
    parser.add_argument("output_dir", type=Path, help="New local directory inside data/evaluation")
    args = parser.parse_args()
    result = capture(args.candidate_report, args.targets, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
