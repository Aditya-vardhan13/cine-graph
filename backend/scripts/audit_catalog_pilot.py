import argparse
from pathlib import Path

from app.services.catalog_pilot_audit import audit_capture_bundle, render_audit_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a local catalog-pilot capture bundle without network access.")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path, help="Markdown report path; defaults to bundle/capture-audit.md")
    args = parser.parse_args()
    report = audit_capture_bundle(args.bundle)
    output = args.output or args.bundle / "capture-audit.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_audit_markdown(report), encoding="utf-8")
    print(f"report: {output.resolve()}")
    print(f"films: {report['audited_films']}/{report['requested_films']}; "
          f"passages: {report['total_passages']}; pass: {report['identity_and_capture_pass']}")
    if not report["identity_and_capture_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
