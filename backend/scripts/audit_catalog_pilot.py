import argparse
from pathlib import Path
import re

from app.services.catalog_pilot_audit import audit_capture_bundle, render_audit_markdown
from app.services.catalog_pilot_capture import _atomic_write


def next_audit_output(bundle: Path) -> Path:
    """Choose a new immutable Markdown report version for this capture bundle."""
    versions = []
    for path in bundle.glob("capture-audit-v*.md"):
        match = re.fullmatch(r"capture-audit-v(\d+)\.md", path.name)
        if match:
            versions.append(int(match.group(1)))
    return bundle / f"capture-audit-v{max(versions, default=0) + 1}.md"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a local catalog-pilot capture bundle without network access.")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--output", type=Path, help="Markdown report path; defaults to the next immutable bundle version")
    args = parser.parse_args()
    report = audit_capture_bundle(args.bundle)
    output = args.output or next_audit_output(args.bundle)
    output.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(output, render_audit_markdown(report).encode("utf-8"))
    print(f"report: {output.resolve()}")
    print(f"integrity: {report['audited_films']}/{report['requested_films']}; "
          f"passages: {report['total_passages']}; "
          f"plot gaps: {report['content_coverage']['plot']['films_missing_section']}; "
          f"production gaps: {report['content_coverage']['production']['films_missing_section']}; "
          f"pass: {report['identity_and_capture_pass']}")
    if not report["identity_and_capture_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
