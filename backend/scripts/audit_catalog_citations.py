import argparse
import json
from pathlib import Path

from app.services.catalog_citation_audit import audit_catalog_citations, render_catalog_citation_audit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve passage citation markers against a retained catalog-pilot HTML bundle; no network."
    )
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    report = audit_catalog_citations(args.bundle)
    json_path = args.bundle / "citation-target-audit.json"
    markdown_path = args.bundle / "citation-target-audit.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_catalog_citation_audit(report), encoding="utf-8")
    totals = report["totals"]
    print(f"report: {markdown_path.resolve()}")
    print(f"films: {totals['films']}; passages: {totals['passages']}; "
          f"reference-list entries: {totals['reference_list_marker_occurrences']}/{totals['marker_occurrences']}; "
          f"URL-linked markers: {totals['external_url_marker_occurrences']}/{totals['marker_occurrences']}")


if __name__ == "__main__":
    main()
