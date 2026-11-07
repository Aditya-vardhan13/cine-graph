"""Create a versioned local-only recheck of previously unmapped pilot snapshots."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from app.services.pilot_snapshot_recheck import recheck_unmapped_pilot_snapshots


DEFAULT_INPUT = Path("data/evaluation/catalog-pilot-metadata-audit-v11.json")
DEFAULT_OUTPUT = Path("data/evaluation/catalog-pilot-snapshot-recheck-v2.json")


def local_evaluation_path(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Pilot recheck inputs and outputs must stay under {root}.")
    return resolved


def build_report(input_path: Path) -> dict[str, Any]:
    data = input_path.read_bytes()
    audit = json.loads(data)
    report = recheck_unmapped_pilot_snapshots(
        audit, audit_sha256=hashlib.sha256(data).hexdigest(),
        allowed_snapshot_root=Path.cwd() / "data/raw-snapshots",
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    evaluation_root = (Path.cwd() / "data/evaluation").resolve()
    input_path = local_evaluation_path(args.input, evaluation_root)
    output_path = local_evaluation_path(args.output, evaluation_root)
    if output_path.exists():
        raise ValueError(f"Refusing to overwrite existing report: {output_path}")
    report = build_report(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({
        "input": str(input_path), "output": str(output_path),
        "previously_unmapped": report["previously_unmapped_snapshot_count"],
        "local_recheck_status_counts": report["local_recheck_status_counts"],
    }, indent=2))


if __name__ == "__main__":
    main()
