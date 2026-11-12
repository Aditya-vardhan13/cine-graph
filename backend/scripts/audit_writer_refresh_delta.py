"""Compare retained refresh passages with existing passages, without publishing them."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import NarrativePassage, SourceSnapshot
from app.services.wikipedia_article_html import parse_article_html
from scripts.capture_credit_targets import save_checkpoint
from scripts.capture_writer_identity_recovery import local_output
from scripts.capture_writer_wikipedia_refresh import targets, verified_checkpoint


def story(locator: str) -> bool:
    return locator.split("/", 1)[0] in {"plot", "plot-summary", "synopsis"}


def measurements(passages) -> dict:
    selected = [content for locator, content in passages if story(locator)]
    return {"passages": len(selected), "characters": sum(len(content) for content in selected)}


def classify(old: dict, new: dict) -> str:
    if not new["characters"]:
        return "new_story_missing" if old["characters"] else "story_missing_both"
    if not old["characters"]:
        return "story_newly_available"
    if new["characters"] < old["characters"] * 0.7:
        return "possible_story_loss"
    return "story_present_both"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit", type=Path)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--output", type=Path, help="Optional local review report")
    args = parser.parse_args()
    audit_bytes = args.audit.read_bytes()
    rows = targets(json.loads(audit_bytes))
    rows_by_qid = {row["wikidata_id"]: row for row in rows}
    state = verified_checkpoint(args.capture_dir, hashlib.sha256(audit_bytes).hexdigest(), rows_by_qid)
    eligible = {qid: capture for qid, capture in state["captures"].items() if capture["status"] == "review_candidate"}
    snapshot_ids = [UUID(capture["prior_snapshot_id"]) for capture in eligible.values()]
    old_passages = defaultdict(list)
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        snapshots = {str(s.id): s for s in db.scalars(select(SourceSnapshot).where(SourceSnapshot.id.in_(snapshot_ids)))}
        for snapshot_id, locator, content in db.execute(select(NarrativePassage.source_snapshot_id,
                NarrativePassage.section_locator, NarrativePassage.content).where(NarrativePassage.source_snapshot_id.in_(snapshot_ids))):
            old_passages[str(snapshot_id)].append((locator, content))
        results = []
        for qid, capture in eligible.items():
            prior = snapshots.get(capture["prior_snapshot_id"])
            if prior is None or prior.content_hash != capture["prior_sha256"]:
                raise ValueError(f"Pinned old snapshot absent or changed: {qid}")
            payload = (args.capture_dir / "snapshots" / f"{capture['sha256']}.html").read_bytes()
            document = parse_article_html(payload, canonical_url=capture["canonical_url"], expected_qid=qid)
            old = measurements(old_passages[capture["prior_snapshot_id"]])
            new = measurements((passage.section_locator, passage.content) for passage in document.passages)
            results.append({"qid": qid, "title": rows_by_qid[qid]["film_title"],
                            "prior_snapshot_id": capture["prior_snapshot_id"],
                            "prior_sha256": capture["prior_sha256"], "capture_sha256": capture["sha256"],
                            "old_revision": capture["prior_revision"], "new_revision": capture["metadata"]["revision_id"],
                            "old": old, "new": new, "classification": classify(old, new)})
    counts = defaultdict(int)
    for row in results:
        counts[row["classification"]] += 1
    report = {"schema": "cinegraph.writer-refresh-story-delta/v1", "review_status": "review_required",
              "audit_sha256": hashlib.sha256(audit_bytes).hexdigest(),
              "limitations": "Character counts are mechanical leads, not quality or rights approval; old counts depend on retained passage extraction.",
              "captured": len(state["captures"]), "compared": len(results), "counts": dict(counts), "entries": results}
    if args.output:
        output = local_output(args.output)
        save_checkpoint(output, report)
        print(json.dumps({key: value for key, value in report.items() if key != "entries"}, sort_keys=True))
    else:
        print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
