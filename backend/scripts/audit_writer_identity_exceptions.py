"""Inspect quarantined identity captures against retained Wikipedia revisions.

This is a read-only review aid. Matching a title is not proof of a redirect,
identity, licensing, or permission to use the source in a model.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import SourceObject, SourceSnapshot
from scripts.audit_writer_identity_recovery import audit_recovery
from scripts.audit_writer_source_identity import read_snapshot, wiki_title
from scripts.capture_writer_identity_recovery import local_output


def classify_exception(*, url_title: str | None, captured_title: str | None,
                       sitelink_title: str | None, expected_page_id: str,
                       captured_page_id: object, expected_revision: object,
                       captured_revision: object) -> str:
    """Classify source observations without resolving the film identity."""
    if not captured_title or not captured_page_id or not captured_revision:
        return "incomplete_wikipedia_observation"
    if (expected_page_id != f"enwiki:{captured_page_id}"
            or str(expected_revision) != str(captured_revision)):
        return "wikipedia_identity_or_revision_conflict"
    if sitelink_title is None:
        return "wikidata_sitelink_missing"
    if sitelink_title != captured_title:
        return "wikidata_sitelink_conflicts_with_retained_title"
    if url_title != captured_title:
        return "retained_title_matches_sitelink_url_differs"
    return "retained_title_and_sitelink_match"


def review_exceptions(db, audit_path: Path, recovery_dir: Path, recovery_audit_path: Path) -> dict:
    recorded_bytes = recovery_audit_path.read_bytes()
    recorded = json.loads(recorded_bytes)
    if recorded != audit_recovery(audit_path, recovery_dir) or not recorded.get("complete"):
        raise ValueError("Recovery audit does not match complete captured inputs")
    original_bytes = audit_path.read_bytes()
    original = json.loads(original_bytes)
    original_by_qid = {entry["wikidata_id"]: entry for entry in original["entries"]}
    checkpoint = json.loads((recovery_dir / "checkpoint.json").read_bytes())
    exceptions = [entry for entry in recorded["entries"] if not entry["mechanical_checks_passed"]]
    ids = [UUID(original_by_qid[entry["qid"]]["wikipedia_snapshot_id"]) for entry in exceptions]
    rows = db.execute(select(SourceSnapshot, SourceObject)
        .join(SourceObject, SourceObject.id == SourceSnapshot.source_object_id)
        .where(SourceSnapshot.id.in_(ids))).all()
    snapshots = {str(snapshot.id): (snapshot, obj) for snapshot, obj in rows}
    results = []
    for entry in exceptions:
        qid = entry["qid"]
        old = original_by_qid[qid]
        capture = checkpoint["captures"][qid]
        issues = []
        title = page_id = revision = None
        row = snapshots.get(old["wikipedia_snapshot_id"])
        if row is None:
            issues.append("wikipedia_snapshot_descriptor_missing")
        else:
            snapshot, obj = row
            if (snapshot.content_hash != old["wikipedia_sha256"]
                    or snapshot.canonical_url != old["wikipedia_url"]
                    or str(snapshot.source_revision) != str(old["wikipedia_revision"])
                    or obj.external_id != old["wikipedia_page_id"]):
                issues.append("wikipedia_snapshot_descriptor_changed")
            try:
                payload = read_snapshot(snapshot)
                parsed = payload.get("parse") or {}
                page = payload.get("page") or {}
                title = parsed.get("title") or page.get("title")
                page_id = parsed.get("pageid") or page.get("pageid")
                revision = parsed.get("revid") or ((page.get("revisions") or [{}])[0]).get("revid")
            except (OSError, ValueError, TypeError, KeyError):
                issues.append("wikipedia_snapshot_unavailable_or_invalid")
        classification = classify_exception(
            url_title=wiki_title(old["wikipedia_url"]), captured_title=title,
            sitelink_title=capture.get("new_sitelink_title"), expected_page_id=old["wikipedia_page_id"],
            captured_page_id=page_id, expected_revision=old["wikipedia_revision"], captured_revision=revision,
        )
        results.append({"qid": qid, "film_title": entry["film_title"],
                        "wikipedia_snapshot_id": old["wikipedia_snapshot_id"],
                        "wikipedia_sha256": old["wikipedia_sha256"],
                        "wikidata_sha256": entry["new_sha256"],
                        "url_title": wiki_title(old["wikipedia_url"]), "retained_title": title,
                        "retained_page_id": page_id, "retained_revision": revision,
                        "new_sitelink_title": capture.get("new_sitelink_title"),
                        "classification": classification, "issues": issues,
                        "identity_status": "review_required", "rights_status": "review_required"})
    return {"schema": "cinegraph.writer-identity-exceptions/v1",
            "source_audit_sha256": sha256(original_bytes).hexdigest(),
            "recovery_audit_sha256": sha256(recorded_bytes).hexdigest(),
            "review_status": "review_required", "entries": results,
            "note": "Source observations only; no redirect, identity or rights decision is made."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("recovery_dir", type=Path)
    parser.add_argument("recovery_audit", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = local_output(args.output)
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing review report")
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        report = review_exceptions(db, args.audit, local_output(args.recovery_dir), args.recovery_audit)
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(data)
    print(json.dumps({"output": str(output), "sha256": sha256(data).hexdigest(),
                      "exceptions": len(report["entries"])}))


if __name__ == "__main__":
    main()
