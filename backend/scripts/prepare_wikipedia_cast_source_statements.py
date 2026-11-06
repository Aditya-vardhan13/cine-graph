"""Prepare an immutable, review-only SourceAssertion draft bundle offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from pathlib import PurePosixPath

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_cast_source_statements import build_source_statement_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = PROJECT_ROOT / "data" / "evaluation"


def _read_input(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Inputs must be regular, non-symlink JSON files")
    resolved = path.resolve(strict=True)
    if EVALUATION_ROOT.resolve(strict=True) not in resolved.parents:
        raise ValueError("Source manifests must remain inside local data/evaluation")
    raw = resolved.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Candidate report root must be an object")
    return value, raw


def _read_actor_snapshots(label_dir: Path, checkpoint: dict, candidate_report: dict) -> dict[str, bytes]:
    if label_dir.is_symlink() or not label_dir.is_dir():
        raise ValueError("Credit-label snapshot directory must be a local regular directory")
    root = label_dir.resolve(strict=True)
    captured = checkpoint.get("captured")
    candidates = candidate_report.get("candidates")
    if not isinstance(captured, dict) or not isinstance(candidates, list):
        raise ValueError("Credit-label checkpoint or candidate report rows are malformed")
    qids = {
        row.get("actor_qid") for row in candidates
        if isinstance(row, dict) and isinstance(row.get("actor_qid"), str)
    }
    payloads: dict[str, bytes] = {}
    for qid in qids:
        record = captured.get(qid)
        relative = record.get("snapshot_path") if isinstance(record, dict) else None
        if not isinstance(relative, str):
            raise ValueError(f"No retained person snapshot is recorded for {qid}")
        rel_path = PurePosixPath(relative)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise ValueError("Person snapshot path must remain within its capture directory")
        candidate_path = root.joinpath(*rel_path.parts)
        if candidate_path.is_symlink() or not candidate_path.is_file():
            raise ValueError(f"Person snapshot must be a regular file for {qid}")
        resolved = candidate_path.resolve(strict=True)
        if root not in resolved.parents:
            raise ValueError("Person snapshot path escapes its capture directory")
        payloads[qid] = resolved.read_bytes()
    return payloads


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_report", type=Path, help="Retained v7 Wikipedia cast candidate report")
    parser.add_argument("capture_manifest", type=Path, help="Exact capture manifest hashed by the candidate report")
    parser.add_argument("credit_target_manifest", type=Path, help="Exact Wikidata P161 target manifest hashed by the candidate report")
    parser.add_argument("output", type=Path, help="New ignored local JSON output; existing files are not overwritten")
    args = parser.parse_args()
    if args.output.is_symlink():
        raise ValueError("Output cannot be a symlink")
    output_path = args.output.resolve()
    evaluation_root = EVALUATION_ROOT.resolve(strict=True)
    if evaluation_root not in output_path.parents:
        raise ValueError("Output must remain inside the local data/evaluation directory")
    report, raw = _read_input(args.candidate_report)
    capture, capture_raw = _read_input(args.capture_manifest)
    targets, targets_raw = _read_input(args.credit_target_manifest)
    label_dir = args.candidate_report.parent / "credit-labels-v1"
    checkpoint, checkpoint_raw = _read_input(label_dir / "checkpoint.json")
    actor_snapshot_bytes = _read_actor_snapshots(label_dir, checkpoint, report)
    result = build_source_statement_manifest(
        report, raw, capture, capture_raw, targets, targets_raw,
        checkpoint, checkpoint_raw, actor_snapshot_bytes,
    )
    payload = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    _write_immutable(output_path, payload)
    print(json.dumps({**result["summary"], "input_sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
