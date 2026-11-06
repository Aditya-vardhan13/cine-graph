"""Validate, combine, and render the retained English-100 cast review queue."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.wikipedia_cast_candidate_coverage import (
    build_cast_candidate_coverage,
    render_cast_candidate_coverage,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_ROOT = PROJECT_ROOT / "data" / "evaluation"


def _read(path: Path) -> tuple[dict, bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Input must be a regular non-symlink JSON file: {path}")
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Input JSON root must be an object: {path}")
    return value, raw


def _write(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise ValueError(f"Output cannot be a symlink: {path}")
    resolved = path.resolve()
    if EVALUATION_ROOT.resolve(strict=True) not in resolved.parents:
        raise ValueError("Outputs must remain under local data/evaluation")
    _write_immutable(resolved, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-report", type=Path, action="append", required=True,
                        help="Partition report; repeat once per disjoint rank range")
    parser.add_argument("--statement-manifest", type=Path, action="append", required=True,
                        help="Exact-input review-only statement bundle; repeat per candidate report")
    parser.add_argument("--pilot-manifest", type=Path, required=True,
                        help="Frozen English pilot manifest that defines expected rank/QID/title/year")
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--expected-film-count", type=int, default=100)
    args = parser.parse_args()
    candidate_inputs = [_read(path) for path in args.candidate_report]
    statement_inputs = [_read(path) for path in args.statement_manifest]
    pilot_input = _read(args.pilot_manifest)
    report = build_cast_candidate_coverage(
        candidate_inputs, statement_inputs, pilot_input,
        expected_film_count=args.expected_film_count,
    )
    json_payload = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    markdown_payload = render_cast_candidate_coverage(report).encode()
    _write(args.json_output, json_payload)
    _write(args.markdown_output, markdown_payload)
    print(json.dumps({
        **report["summary"],
        "json_sha256": hashlib.sha256(json_payload).hexdigest(),
        "markdown_sha256": hashlib.sha256(markdown_payload).hexdigest(),
        "json_output": str(args.json_output),
        "markdown_output": str(args.markdown_output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
