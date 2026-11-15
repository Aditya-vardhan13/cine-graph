"""Read-only coverage audit of current passages for a pinned film identity audit.

This reports source availability, not accuracy, rights approval or retrieval quality.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Film, SourceObject
from app.services.current_narrative_passages import current_passage_rows
from app.services.narrative_use_decisions import latest_decisions
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.source_rights_policy import can_use_narrative_semantically


def audit(db, entries: list[dict]) -> dict:
    ids = [UUID(entry["film_entity_id"]) for entry in entries]
    if len(ids) != len(set(ids)):
        raise ValueError("Identity audit contains duplicate film entities")
    profiles = set(db.scalars(select(Film.entity_id).where(Film.entity_id.in_(ids))))
    counts = Counter(entries=len(entries))
    exceptions = []
    for start in range(0, len(entries), 50):
        batch = entries[start:start + 50]
        rows = current_passage_rows(db, {UUID(entry["film_entity_id"]) for entry in batch})
        objects = {obj.id: obj for obj in db.scalars(select(SourceObject).where(
            SourceObject.id.in_({snapshot.source_object_id for _, snapshot in rows})))}
        by_entity = defaultdict(list)
        for passage, snapshot in rows:
            by_entity[passage.subject_entity_id].append((passage, snapshot))
        decisions = latest_decisions(db, {snapshot.id for _, snapshot in rows})
        for entry in batch:
            entity_id = UUID(entry["film_entity_id"])
            wiki = [(p, s) for p, s in by_entity[entity_id]
                    if objects[s.source_object_id].external_id == entry["wikipedia_page_id"]]
            snapshots = {s.id: s for _, s in wiki}
            issues = []
            if entity_id not in profiles:
                issues.append("film_profile_missing")
            if len(snapshots) != 1:
                issues.append("current_wikipedia_snapshot_not_unique")
            else:
                snapshot = next(iter(snapshots.values()))
                integrity = verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size)
                counts[f"current_source_{integrity}"] += 1
                if integrity != "verified":
                    issues.append(f"source_{integrity}")
                decision = decisions.get(snapshot.id)
                approved = can_use_narrative_semantically(
                    decision=decision.decision if decision else None,
                    basis_url=decision.decision_basis_url if decision else None,
                    notes=decision.decision_notes if decision else None,
                    license_name=snapshot.license, attribution_url=snapshot.attribution_url,
                )
                counts["semantic_use_approved" if approved else "semantic_use_not_approved"] += 1
                if not any(p.section_locator.split("/")[0] in {"plot", "plot-summary", "synopsis"}
                           for p, _ in wiki):
                    issues.append("no_standard_story_section")
                counts["current_wikipedia_passages"] += len(wiki)
            if issues:
                exceptions.append({"film": entry["film_title"], "qid": entry["wikidata_id"], "issues": issues})
    return {"counts": dict(sorted(counts.items())), "exceptions": exceptions,
            "caveat": "Coverage only; source integrity and section presence do not prove accuracy or relevance."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("identity_audit", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    content = args.identity_audit.read_bytes()
    if hashlib.sha256(content).hexdigest() != args.sha256:
        raise ValueError("Identity audit hash mismatch")
    document = json.loads(content)
    with SessionLocal() as db:
        report = audit(db, document["entries"])
    report["identity_audit_sha256"] = args.sha256
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
