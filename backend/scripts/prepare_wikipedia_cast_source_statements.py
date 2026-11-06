"""Prepare an immutable, review-only SourceAssertion draft bundle offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_cast_source_statements import build_source_statement_manifest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = PROJECT_ROOT / "data" / "evaluation"


def _read_input(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Input must be a regular, non-symlink candidate report")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Candidate report root must be an object")
    return value, raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_report", type=Path, help="Retained v7 Wikipedia cast candidate report")
    parser.add_argument("output", type=Path, help="New ignored local JSON output; existing files are not overwritten")
    args = parser.parse_args()
    if args.output.is_symlink():
        raise ValueError("Output cannot be a symlink")
    output_path = args.output.resolve()
    evaluation_root = EVALUATION_ROOT.resolve(strict=True)
    if evaluation_root not in output_path.parents:
        raise ValueError("Output must remain inside the local data/evaluation directory")
    report, raw = _read_input(args.candidate_report)
    result = build_source_statement_manifest(report, raw)
    payload = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    _write_immutable(output_path, payload)
    print(json.dumps({**result["summary"], "input_sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))


if __name__ == "__main__":
    main()
