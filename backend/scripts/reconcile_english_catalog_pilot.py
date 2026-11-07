"""Reconcile retained English-pilot captures offline into versioned local reports."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from app.services.catalog_pilot_audit import audit_capture_bundle
from app.services.catalog_pilot_capture import _atomic_write
from app.services.english_catalog_pilot_reconciliation import (
    reconcile_english_pilot_captures,
    render_reconciliation_markdown,
)


DEFAULT_PILOT = Path("data/evaluation/catalog-pilot-english100-v1.json")
DEFAULT_BATCHES = (
    Path("data/evaluation/catalog-intake/first10-v1"),
    Path("data/evaluation/catalog-intake/english100-rank11-100-v1"),
)
DEFAULT_JSON = Path("data/evaluation/english100-capture-reconciliation-v7.json")
DEFAULT_MARKDOWN = Path("data/evaluation/english100-capture-reconciliation-v7.md")


def _local_evaluation_path(path: Path, evaluation_root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(evaluation_root):
        raise ValueError(f"All pilot inputs and reports must stay under {evaluation_root}.")
    return resolved


def build_reconciliation(project_root: Path, *, pilot_path: Path, batches: tuple[Path, ...]) -> dict[str, Any]:
    """Verify capture bundles and reconcile them against the exact frozen pilot."""
    evaluation_root = (project_root / "data/evaluation").resolve()
    pilot_file = _local_evaluation_path(project_root / pilot_path, evaluation_root)
    pilot_bytes = pilot_file.read_bytes()
    pilot = json.loads(pilot_bytes)
    bundle_inputs = []
    for batch_path in batches:
        batch = _local_evaluation_path(project_root / batch_path, evaluation_root)
        manifest = json.loads((batch / "capture-manifest.json").read_text(encoding="utf-8"))
        audit = audit_capture_bundle(batch)
        bundle_inputs.append((batch.name, manifest, audit))
    return reconcile_english_pilot_captures(
        pilot, bundle_inputs, pilot_sha256=sha256(pilot_bytes).hexdigest(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--first-ten", type=Path, default=DEFAULT_BATCHES[0])
    parser.add_argument("--rank-11-100", type=Path, default=DEFAULT_BATCHES[1])
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args()

    project_root = Path.cwd().resolve()
    evaluation_root = (project_root / "data/evaluation").resolve()
    json_output = _local_evaluation_path(project_root / args.json_output, evaluation_root)
    markdown_output = _local_evaluation_path(project_root / args.markdown_output, evaluation_root)
    if json_output == markdown_output:
        raise ValueError("JSON and Markdown reports must use distinct versioned paths.")
    report = build_reconciliation(
        project_root, pilot_path=args.pilot,
        batches=(args.first_ten, args.rank_11_100),
    )
    json_bytes = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    markdown_bytes = render_reconciliation_markdown(report).encode("utf-8")
    _atomic_write(json_output, json_bytes)
    _atomic_write(markdown_output, markdown_bytes)

    print(f"JSON report: {json_output}")
    print(f"Markdown report: {markdown_output}")
    print(f"Integrity: {report['captured_films']}/{report['expected_films']}; "
          f"passages: {report['passages']}; short/long flags: "
          f"{report['passages_under_80_chars']}/{report['passages_over_2500_chars']}; "
          f"plot gaps: {report['content_coverage']['plot']['films_missing_section']}; "
          f"production gaps: {report['content_coverage']['production']['films_missing_section']}")


if __name__ == "__main__":
    main()
