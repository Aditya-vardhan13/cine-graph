"""Build an immutable local credit-target manifest; never contacts the network."""
import argparse
import json
from pathlib import Path

from app.services.catalog_pilot_reextract import _write_immutable
from app.services.credit_target_manifest import select_credit_targets

parser = argparse.ArgumentParser()
parser.add_argument("bundle", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
result = select_credit_targets(args.bundle)
_write_immutable(args.output, (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
print(f"films: {result['films']}; unique targets: {len(result['targets'])}; exceptions: {len(result['exceptions'])}; deprecated skipped: {result['deprecated_skipped']}")
