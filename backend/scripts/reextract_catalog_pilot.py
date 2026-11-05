import argparse
import json
from pathlib import Path

from app.services.catalog_pilot_reextract import audit_catalog_pilot_extraction, derive_catalog_pilot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a new versioned passage derivative from retained pilot source bytes; no network."
    )
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    manifest = derive_catalog_pilot(args.bundle)
    report = audit_catalog_pilot_extraction(args.bundle, manifest)
    version = manifest["parser_version"].rsplit("-v", 1)[-1]
    audit_path = args.bundle / f"extraction-audit-v{version}.json"
    audit_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"audit: {audit_path.resolve()}")
    print(f"parser: {report['parser_version']}; films: {report['audited_films']}/{report['requested_films']}; "
          f"passages: {report['total_passages']}; citation markers: {report['citation_marker_occurrences']}; "
          f"pass: {report['pass']}")
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
