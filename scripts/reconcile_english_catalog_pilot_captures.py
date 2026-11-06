"""Reconcile audited source captures to the frozen local English 100 pilot."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from app.services.catalog_pilot_audit import audit_capture_bundle
from app.services.english_catalog_pilot_reconciliation import (
    reconcile_english_pilot_captures,
    render_reconciliation_markdown,
)


def _within(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=Path("data/evaluation/catalog-pilot-english100-v1.json"))
    parser.add_argument("--first-ten", type=Path, default=Path("data/evaluation/catalog-intake/first10-v1"))
    parser.add_argument("--rank-11-100", type=Path, default=Path("data/evaluation/catalog-intake/english100-rank11-100-v1"))
    parser.add_argument("--output-json", type=Path, default=Path("data/evaluation/english100-capture-reconciliation-v4.json"))
    parser.add_argument("--output-markdown", type=Path, default=Path("data/evaluation/english100-capture-reconciliation-v4.md"))
    args = parser.parse_args()

    project = Path.cwd().resolve()
    evaluation = (project / "data/evaluation").resolve()
    inputs = (args.pilot, args.first_ten, args.rank_11_100)
    outputs = (args.output_json, args.output_markdown)
    if any(not _within(path, evaluation) for path in (*inputs, *outputs)):
        parser.error("All inputs and outputs must stay under local data/evaluation")
    if not args.pilot.is_file():
        parser.error(f"Missing English pilot manifest: {args.pilot}")
    for directory in (args.first_ten, args.rank_11_100):
        if not (directory / "capture-manifest.json").is_file():
            parser.error(f"Missing capture manifest in {directory}")
    if any(path.exists() for path in outputs):
        parser.error("Refusing to overwrite an existing versioned reconciliation report")

    pilot_bytes = args.pilot.read_bytes()
    pilot = json.loads(pilot_bytes)
    bundles = []
    for label, directory in (("ranks 1-10 (earlier capture)", args.first_ten),
                             ("ranks 11-100", args.rank_11_100)):
        manifest = json.loads((directory / "capture-manifest.json").read_text(encoding="utf-8"))
        audit = audit_capture_bundle(directory)
        bundles.append((label, manifest, audit))
    report = reconcile_english_pilot_captures(pilot, bundles, pilot_sha256=sha256(pilot_bytes).hexdigest())
    json_bytes = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    markdown = render_reconciliation_markdown(report)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_bytes(json_bytes)
    args.output_markdown.write_text(markdown, encoding="utf-8")
    print(json.dumps({
        "films": report["captured_films"],
        "passages": report["passages"],
        "content_gaps": len(report["content_gaps"]),
        "output_json": str(args.output_json),
        "output_markdown": str(args.output_markdown),
    }, indent=2))


if __name__ == "__main__":
    main()
