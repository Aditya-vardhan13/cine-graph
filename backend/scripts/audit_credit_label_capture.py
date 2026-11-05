"""Audit a completed local Wikidata credit-label capture bundle offline."""
import argparse
import json
from pathlib import Path

from app.services.credit_label_capture_audit import audit_credit_label_capture

parser = argparse.ArgumentParser()
parser.add_argument("manifest", type=Path)
parser.add_argument("capture_dir", type=Path)
parser.add_argument("--output", type=Path)
args = parser.parse_args()
result = audit_credit_label_capture(args.manifest, args.capture_dir)
rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite audit report: {args.output}")
    args.output.write_text(rendered, encoding="utf-8")
print(rendered, end="")
