"""Audit a title/year selection against retained Wikipedia and Wikidata evidence.

This command is intentionally read-only.  It validates the final catalogue
membership from raw source assertions rather than trusting a successful job
exit: every selected title must map to one Wikipedia QID, whose Wikidata
evidence has an accepted film type and the selected release year.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RawIngestionRun, RawIngestionRunSnapshot, SourceAssertion, SourceSnapshot
from app.services.wikipedia_raw import read_manifest

FILM_TYPE_QIDS = {"Q11424", "Q202866", "Q20650540"}


def snak_entity_id(raw_value: dict[str, Any]) -> str | None:
    value = raw_value.get("datavalue", {}).get("value", {})
    return value.get("id") if isinstance(value, dict) and isinstance(value.get("id"), str) else None


def snak_year(raw_value: dict[str, Any]) -> int | None:
    value = raw_value.get("datavalue", {}).get("value", {})
    stamp = value.get("time") if isinstance(value, dict) else None
    match = re.match(r"[+-](\d{4})-", stamp) if isinstance(stamp, str) else None
    return int(match.group(1)) if match else None


def wikipedia_release_years(payload: dict[str, Any]) -> set[int]:
    """Extract years only from the revision's infobox ``released`` field.

    This is intentionally narrow. It does not treat arbitrary prose years as
    release evidence, and exists for documented source-date disagreements
    where Wikidata records a festival/first publication date instead.
    """
    page = payload.get("page", {})
    revision = (page.get("revisions") or [{}])[0]
    content = revision.get("slots", {}).get("main", {}).get("content", "")
    match = re.search(r"^\s*\|\s*released\s*=\s*(.*)$", content, flags=re.IGNORECASE | re.MULTILINE)
    return {int(year) for year in re.findall(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)", match.group(1))} if match else set()


def snapshot_positions(snapshots: list[SourceSnapshot]) -> tuple[dict[int, str], dict[int, set[int]], list[str]]:
    """Read only recent host-visible source snapshots to bind positions to QIDs."""
    qid_by_position: dict[int, str] = {}
    wikipedia_years_by_position: dict[int, set[int]] = {}
    unavailable: list[str] = []
    for item in snapshots:
        if not item.storage_uri:
            unavailable.append(str(item.id))
            continue
        path = Path(item.storage_uri.removeprefix("file://"))
        if not path.exists():
            unavailable.append(str(item.id))
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        entry = payload.get("manifest_entry", {})
        page = payload.get("page", {})
        position = entry.get("position")
        qid = page.get("pageprops", {}).get("wikibase_item")
        if isinstance(position, int) and isinstance(qid, str):
            qid_by_position[position] = qid
            wikipedia_years_by_position[position] = wikipedia_release_years(payload)
    return qid_by_position, wikipedia_years_by_position, unavailable


def audit_selection(db: Session, entries: list[dict[str, Any]], manifest_uris: list[str]) -> dict[str, Any]:
    runs = db.scalars(select(RawIngestionRun).where(
        RawIngestionRun.manifest_uri.in_(manifest_uris), RawIngestionRun.status == "complete",
    )).all()
    run_snapshot_ids: dict[str, list[Any]] = defaultdict(list)
    for run in runs:
        run_snapshot_ids[run.adapter_name].extend(db.scalars(select(RawIngestionRunSnapshot.source_snapshot_id).where(
            RawIngestionRunSnapshot.ingestion_run_id == run.id,
        )).all())
    wiki_snapshots = db.scalars(select(SourceSnapshot).where(
        SourceSnapshot.id.in_(run_snapshot_ids["wikipedia_api_revision_snapshot"])
    )).all() if run_snapshot_ids["wikipedia_api_revision_snapshot"] else []
    qid_by_position, wikipedia_years_by_position, unavailable_snapshot_files = snapshot_positions(wiki_snapshots)

    qids = set(qid_by_position.values())
    facts: dict[str, dict[str, set[Any]]] = defaultdict(lambda: {"types": set(), "years": set()})
    for assertion in db.scalars(select(SourceAssertion).where(SourceAssertion.source_property.in_(("P31", "P577")))).all():
        qid = assertion.raw_subject.get("wikidata_id")
        if qid not in qids:
            continue
        if assertion.source_property == "P31":
            value = snak_entity_id(assertion.raw_value)
            if value:
                facts[qid]["types"].add(value)
        else:
            year = snak_year(assertion.raw_value)
            if year:
                facts[qid]["years"].add(year)

    missing: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    seen_qids: list[str] = []
    for entry in entries:
        position = int(entry["position"])
        qid = qid_by_position.get(position)
        if not qid:
            missing.append({"position": position, "title": entry["title"], "reason": "missing readable Wikipedia revision snapshot"})
            continue
        seen_qids.append(qid)
        item_facts = facts[qid]
        reasons: list[str] = []
        if not item_facts["types"] & FILM_TYPE_QIDS:
            reasons.append(f"not an accepted film type: {sorted(item_facts['types'])}")
        expected_year = int(entry["release_year"])
        if expected_year not in item_facts["years"] and expected_year not in wikipedia_years_by_position.get(position, set()):
            reasons.append(
                f"release year absent from Wikidata and Wikipedia infobox: "
                f"wikidata={sorted(item_facts['years'])}, wikipedia={sorted(wikipedia_years_by_position.get(position, set()))}"
            )
        if reasons:
            invalid.append({"position": position, "title": entry["title"], "qid": qid, "reasons": reasons})

    verified = len(entries) - len(missing) - len(invalid)
    return {
        "manifest_entries": len(entries),
        "complete_runs": len(runs),
        "wikipedia_revision_snapshots": len(wiki_snapshots),
        "position_to_qid_links": len(qid_by_position),
        "verified_identity_type_year": verified,
        "coverage_percent": round(100 * verified / len(entries), 2) if entries else 0,
        "duplicate_qids": len(seen_qids) - len(set(seen_qids)),
        "unavailable_snapshot_files": unavailable_snapshot_files,
        "missing": missing,
        "invalid": invalid,
        "pass": not missing and not invalid and len(seen_qids) == len(set(seen_qids)),
    }


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Audit selected films against retained raw Wikipedia and Wikidata evidence.")
    parser.add_argument("manifest", type=Path, help="The complete user selection manifest to audit.")
    parser.add_argument("--ingestion-manifest", action="append", required=True, help="Manifest path used by each completed ingestion run; repeat for split runs.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    entries, _ = read_manifest(args.manifest)
    uris = [path.resolve().as_uri() for path in (Path(value) for value in args.ingestion_manifest)]
    with SessionLocal() as db:
        report = audit_selection(db, entries, uris)
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    if not report["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
