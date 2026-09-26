"""Read-only, local writer-task study of the actual comparison API output.

This is a product evaluation, not a new retrieval benchmark or a source crawler.
Reviewer judgments are collected separately; technical checks cannot mark a
comparison useful or a passage factually accurate.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api import compare_film_stories
from app.db import SessionLocal
from app.models import CanonicalEntity, ReferenceCollectionMembership
from app.schemas import StoryComparisonRequest


CATEGORIES = frozenset({
    "character_change", "moral_dilemma", "plot_structure", "worldbuilding",
    "craft", "genre_inversion", "reception_disagreement", "unanswerable",
})
ENTRY_COUNTS = {"pair": 16, "film_first": 2, "question_only": 2}
REVIEW_FIELDS = (
    "useful", "relevant", "evidence_accurate", "useful_contrast",
    "non_obvious", "uncertainty_handled", "writer_next_step",
    "unsupported_claims", "abstained_when_needed",
)


def load_tasks(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    tasks = manifest.get("tasks", [])
    if manifest.get("version") != "writer-study-v1" or len(tasks) != 20:
        raise ValueError("Writer study v1 requires exactly 20 versioned tasks.")
    if not isinstance(manifest.get("collection"), str) or not manifest["collection"]:
        raise ValueError("Writer study collection is required.")
    if Counter(task.get("entry") for task in tasks) != ENTRY_COUNTS:
        raise ValueError("Writer study requires 16 pair, 2 film-first, and 2 question-only tasks.")
    identifiers = [task.get("id") for task in tasks]
    if len(set(identifiers)) != len(identifiers) or any(not isinstance(value, str) for value in identifiers):
        raise ValueError("Writer study task IDs must be unique strings.")
    if {task.get("category") for task in tasks} != CATEGORIES:
        raise ValueError("Writer study must cover all eight declared categories.")
    for task in tasks:
        expected_films = {"pair": 2, "film_first": 1, "question_only": 0}[task["entry"]]
        if len(task.get("films", [])) != expected_films or len(set(task["films"])) != expected_films:
            raise ValueError(f"{task['id']}: incorrect or repeated film identities.")
        if any(not isinstance(qid, str) or not qid.startswith("Q") for qid in task["films"]):
            raise ValueError(f"{task['id']}: films require canonical Wikidata QIDs.")
        if not isinstance(task.get("question"), str) or not 12 <= len(task["question"]) <= 400:
            raise ValueError(f"{task['id']}: question length is outside the product contract.")
    return manifest


def film_ids(db: Session, *, collection: str, qids: set[str]) -> dict[str, UUID]:
    rows = db.execute(
        select(CanonicalEntity.wikidata_id, CanonicalEntity.id)
        .join(ReferenceCollectionMembership, ReferenceCollectionMembership.entity_id == CanonicalEntity.id)
        .where(
            ReferenceCollectionMembership.collection_code == collection,
            ReferenceCollectionMembership.status == "included",
            CanonicalEntity.wikidata_id.in_(qids),
        )
    ).all()
    found = dict(rows)
    if set(found) != qids:
        raise ValueError(f"Study films are absent from the research collection: {sorted(qids - set(found))}")
    return found


def technical_checks(result: dict[str, Any]) -> dict[str, Any]:
    cards = [
        (side, lens[f"{side}_evidence"])
        for lens in result["lenses"] for side in ("first", "second")
    ]
    present = [(side, card) for side, card in cards if card]
    repeated = {
        side: len([card["chunk_id"] for card_side, card in present if card_side == side])
        - len({card["chunk_id"] for card_side, card in present if card_side == side})
        for side in ("first", "second")
    }
    return {
        "displayed_cards": len(present),
        "missing_cards": len(cards) - len(present),
        "cards_without_source_pointer": sum(
            not (card.get("source_url") and card.get("source_revision") and card.get("source_license"))
            for _, card in present
        ),
        "repeated_chunk_ids_by_film": repeated,
        "degraded": result["degraded"],
        "explicit_abstention_available": False,
    }


def run_study(db: Session, manifest: dict[str, Any]) -> dict[str, Any]:
    collection = manifest["collection"]
    qids = {qid for task in manifest["tasks"] for qid in task["films"]}
    identities = film_ids(db, collection=collection, qids=qids)
    results = []
    for task in manifest["tasks"]:
        row: dict[str, Any] = {**task, "status": "not_run"}
        if task["entry"] != "pair":
            row.update({
                "status": "unsupported_entry_flow",
                "reason": "The current product requires two manually selected films before it can answer a writer question.",
            })
        else:
            started = perf_counter()
            try:
                response = compare_film_stories(StoryComparisonRequest(
                    first_entity_id=identities[task["films"][0]],
                    second_entity_id=identities[task["films"][1]],
                    question=task["question"],
                ), db=db).model_dump(mode="json")
                row.update({
                    "status": "displayed",
                    "elapsed_ms": round((perf_counter() - started) * 1000, 2),
                    "comparison": response,
                    "technical_checks": technical_checks(response),
                })
            except Exception as exc:
                row.update({
                    "status": "error",
                    "elapsed_ms": round((perf_counter() - started) * 1000, 2),
                    "error": f"{type(exc).__name__}: {exc}",
                })
        results.append(row)
        print(f"writer study: {task['id']} {row['status']}", flush=True)
    return {
        "version": manifest["version"],
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "collection": collection,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "independent_human_review_required",
        "first_pair_task_id": next(task["id"] for task in manifest["tasks"] if task["entry"] == "pair"),
        "tasks": results,
    }


def render_packet(report: dict[str, Any]) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    sections = []
    for task in report["tasks"]:
        content = [
            f"<section class='task' id='{esc(task['id'])}'><h2>{esc(task['id'])} · {esc(task['category'].replace('_', ' '))}</h2>",
            f"<p class='question'>{esc(task['question'])}</p><p class='status'>Entry: {esc(task['entry'])} · Result: {esc(task['status'])}</p>",
        ]
        if task["status"] == "displayed":
            result = task["comparison"]
            content.append(
                f"<p>{esc(result['first']['title'])} × {esc(result['second']['title'])} · "
                f"{esc(result['retrieval_method'])} · {esc(task['elapsed_ms'])} ms</p>"
            )
            if result.get("fallback_reason"):
                content.append(f"<p class='warn'>{esc(result['fallback_reason'])}</p>")
            for lens in result["lenses"]:
                content.append(f"<div class='lens'><h3>{esc(lens['label'])}</h3><p>{esc(lens['writer_prompt'])}</p><div class='cards'>")
                for side in ("first", "second"):
                    card = lens[f"{side}_evidence"]
                    if card:
                        content.append(
                            f"<article><small>{esc(result[side]['title'])} · {esc(card['section_title'])}</small>"
                            f"<p>{esc(card['excerpt'])}</p><a href='{esc(card['source_url'])}' target='_blank' "
                            f"rel='noopener noreferrer'>Source · {esc(card['source_license'])} · revision {esc(card['source_revision'])}</a></article>"
                        )
                    else:
                        content.append(f"<article><small>{esc(result[side]['title'])}</small><p>No distinct passage available.</p></article>")
                content.append("</div></div>")
            content.append(f"<p class='warn'>{esc(result['caution'])}</p>")
        elif task["status"] == "unsupported_entry_flow":
            content.append(f"<p class='warn'>{esc(task['reason'])}</p>")
        else:
            content.append(f"<p class='warn'>{esc(task.get('error', 'No result'))}</p>")
        content.append("<div class='review'><h3>Independent reviewer judgment</h3>")
        for field in REVIEW_FIELDS:
            content.append(
                f"<label>{esc(field.replace('_', ' '))}<select data-task='{esc(task['id'])}' data-field='{esc(field)}'>"
                "<option value=''>Unrated</option><option value='yes'>Yes</option><option value='no'>No</option>"
                "<option value='unclear'>Unclear</option></select></label>"
            )
        content.append(f"<label>Task time, seconds<input type='number' min='0' data-task='{esc(task['id'])}' data-field='task_seconds'></label>")
        content.append(f"<label>Evidence and decision notes<textarea data-task='{esc(task['id'])}' data-field='notes'></textarea></label></div></section>")
        sections.append("".join(content))
    return """<!doctype html><html lang='en'><meta charset='utf-8'><title>CineGraph writer study</title>
<style>body{background:#0b0d13;color:#ececf4;font:16px system-ui;margin:auto;max-width:1200px;padding:28px}p{line-height:1.5}.task,.lens,article{background:#171a25;border:1px solid #30364a;border-radius:14px;padding:18px;margin:16px 0}.question{font-size:1.25rem}.status,.warn{color:#ffce80}.cards{display:grid;grid-template-columns:1fr 1fr;gap:14px}article{margin:0;white-space:pre-wrap}small{color:#a8d9f9}a{color:#9bdfd3}.review{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.review h3{grid-column:1/-1}label{display:grid;gap:5px}select,input,textarea{background:#0d1018;color:white;border:1px solid #4a536a;padding:8px}textarea{min-height:70px}button{padding:10px 16px;background:#8c6bff;color:white;border:0;border-radius:8px}@media(max-width:750px){.cards,.review{grid-template-columns:1fr}}</style>
<h1>CineGraph writer-task study</h1><p>This packet shows the current comparison API's user-visible evidence. It does not claim usefulness or source accuracy. Review independently; do not use retrieval scores to decide. For unsupported flows, judge the product's inability to complete the task. Record your own task time. No scores are sent to a server.</p>
<label>Reviewer code (not your name)<input id='reviewer' maxlength='40'></label><button id='export'>Download my review JSON</button>
""" + "".join(sections) + """
<script>document.getElementById('export').onclick=()=>{const reviewer=document.getElementById('reviewer').value.trim();if(!reviewer){alert('Enter a reviewer code first.');return}const tasks={};document.querySelectorAll('[data-task]').forEach(el=>{const id=el.dataset.task;(tasks[id]??={})[el.dataset.field]=el.value});const output={version:'writer-study-v1-review',reviewer,created_at:new Date().toISOString(),tasks};const blob=new Blob([JSON.stringify(output,null,2)],{type:'application/json'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='writer-study-review-'+reviewer.replace(/[^a-z0-9_-]/gi,'_')+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000)};</script></html>"""


def aggregate_reviews(report: dict[str, Any], reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the declared product gate only to two complete independent reviews."""
    if len(reviews) != 2 or any(not isinstance(review.get("reviewer"), str) for review in reviews):
        raise ValueError("Exactly two distinct reviewer codes are required.")
    if len({review["reviewer"] for review in reviews}) != 2:
        raise ValueError("Exactly two distinct reviewer codes are required.")
    task_ids = {task["id"] for task in report["tasks"]}
    displayed_ids = {task["id"] for task in report["tasks"] if task["status"] == "displayed"}
    for review in reviews:
        if review.get("version") != "writer-study-v1-review" or not review.get("reviewer"):
            raise ValueError("Reviewer export has an invalid version or reviewer code.")
        if set(review.get("tasks", {})) != task_ids:
            raise ValueError("Every reviewer must rate exactly the 20 study tasks.")
        for task_id, values in review["tasks"].items():
            if any(values.get(field) not in {"yes", "no", "unclear"} for field in REVIEW_FIELDS):
                raise ValueError(f"{task_id}: all review fields require a yes, no, or unclear rating.")
            try:
                elapsed = float(values.get("task_seconds", ""))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{task_id}: task time must be recorded in seconds.") from exc
            if not math.isfinite(elapsed) or elapsed < 0:
                raise ValueError(f"{task_id}: task time must be finite and nonnegative.")
    both_useful = [
        task_id for task_id in sorted(displayed_ids)
        if all(review["tasks"][task_id]["useful"] == "yes" for review in reviews)
    ]
    unsupported_claims = [
        task_id for task_id in sorted(task_ids)
        if any(review["tasks"][task_id]["unsupported_claims"] != "no" for review in reviews)
    ]
    unanswerable_ids = {
        task["id"] for task in report["tasks"] if task["category"] == "unanswerable"
    }
    failed_abstentions = [
        task_id for task_id in sorted(unanswerable_ids)
        if any(review["tasks"][task_id]["abstained_when_needed"] != "yes" for review in reviews)
    ]
    gate = {
        "both_reviewers_useful_at_least_14_of_20": len(both_useful) >= 14,
        "no_unsupported_claims": not unsupported_claims,
        "unanswerable_tasks_abstained": not failed_abstentions,
    }
    return {
        "version": report["version"],
        "reviewer_codes": [review["reviewer"] for review in reviews],
        "both_reviewers_useful_count": len(both_useful),
        "both_reviewers_useful_task_ids": both_useful,
        "unsupported_claim_or_unclear_task_ids": unsupported_claims,
        "failed_or_unclear_abstention_task_ids": failed_abstentions,
        "gate": gate,
        "passed": all(gate.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a read-only local writer-task study packet.")
    parser.add_argument("--manifest", type=Path, default=Path("backend/tests/fixtures/writer-study-v1.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/evaluation/writer-study-v1"))
    parser.add_argument("--reviews", nargs=2, type=Path, metavar=("REVIEW_A", "REVIEW_B"))
    args = parser.parse_args()
    if args.reviews:
        report = json.loads((args.output_dir / "study.json").read_text(encoding="utf-8"))
        reviews = [json.loads(path.read_text(encoding="utf-8")) for path in args.reviews]
        summary = aggregate_reviews(report, reviews)
        (args.output_dir / "review-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return
    manifest = load_tasks(args.manifest)
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        report = run_study(db, manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "study.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.output_dir / "review-packet.html").write_text(render_packet(report), encoding="utf-8")
    print(json.dumps({
        "results": dict(Counter(task["status"] for task in report["tasks"])),
        "review_packet": str(args.output_dir / "review-packet.html"),
        "human_review_required": True,
    }, indent=2))


if __name__ == "__main__":
    main()
