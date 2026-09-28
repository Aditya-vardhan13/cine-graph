"""Capture the current question-first writer journey on a local evaluation copy.

The packet records API output, source pointers, and timing. It never assigns
usefulness or factual-accuracy ratings; two independent people do that later.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import text

from app.api import compare_film_stories, discover_films_for_question
from app.core.config import get_settings
from app.db import SessionLocal
from app.schemas import ResearchDiscoveryRequest, StoryComparisonRequest
from app.services.writer_study import CATEGORIES, aggregate_reviews, film_ids, render_packet, technical_checks


ENTRY_COUNTS = {"pair": 12, "film_first": 4, "question_only": 4}
PASSAGE_LABELS = frozenset({"relevant", "irrelevant", "unclear"})


def expected_passage_sources(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Bind each review control to the captured chunk and immutable source pointer."""
    expected: dict[str, dict[str, Any]] = {}
    for task in report["tasks"]:
        task_id = task["id"]
        selected_count = 1 if task["entry"] == "film_first" else 2
        for lead in task.get("discovery", {}).get("leads", [])[:selected_count]:
            chunk_id = lead.get("chunk_id")
            if not chunk_id:
                raise ValueError(f"{task_id}: recapture discovery with passage IDs before review.")
            expected[f"{task_id}:discovery:{chunk_id}"] = {
                "task_id": task_id, "kind": "discovery", "chunk_id": chunk_id,
                "source_url": lead["source_url"], "source_revision": lead["source_revision"],
                "source_license": lead["source_license"],
            }
        lenses = task.get("comparison", {}).get("lenses", [])
        focus = next((lens for lens in lenses if lens["identifier"] == "central_question"
                      and lens["first_evidence"] and lens["second_evidence"]), None)
        if focus is None:
            focus = next((lens for lens in lenses if lens["first_evidence"] and lens["second_evidence"]), None)
        for lens in (focus,) if focus else ():
            for side in ("first", "second"):
                card = lens.get(f"{side}_evidence")
                if not card:
                    continue
                chunk_id = card["chunk_id"]
                expected[f"{task_id}:comparison:{lens['identifier']}:{side}:{chunk_id}"] = {
                    "task_id": task_id, "kind": "comparison", "chunk_id": chunk_id,
                    "source_url": card["source_url"], "source_revision": card["source_revision"],
                    "source_license": card["source_license"],
                }
    return expected


def aggregate_passage_reviews(report: dict[str, Any], reviews: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure relevance only after two complete, source-bound human exports."""
    if (len(reviews) != 2 or any(not isinstance(review.get("reviewer"), str) or not review["reviewer"]
                                 for review in reviews) or reviews[0]["reviewer"] == reviews[1]["reviewer"]):
        raise ValueError("Exactly two distinct passage reviewers are required.")
    packet_id = hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    expected = expected_passage_sources(report)
    for review in reviews:
        if review.get("packet_id") != packet_id:
            raise ValueError("Passage review belongs to a different study capture.")
        labels = review.get("passages", {})
        pointers = review.get("passage_sources", {})
        if set(labels) != set(expected) or set(pointers) != set(expected):
            raise ValueError("Every captured passage needs one source-bound relevance rating.")
        for passage_id, pointer in expected.items():
            if labels[passage_id] not in PASSAGE_LABELS or pointers[passage_id] != pointer:
                raise ValueError(f"{passage_id}: invalid label or stale source pointer.")
    both_relevant = {
        passage_id for passage_id in expected
        if all(review["passages"][passage_id] == "relevant" for review in reviews)
    }
    agreement = sum(
        reviews[0]["passages"][passage_id] == reviews[1]["passages"][passage_id]
        for passage_id in expected
    )
    selected_discovery: list[tuple[str, ...]] = []
    focus_pairs: list[tuple[str, str]] = []
    per_task: dict[str, dict[str, Any]] = {}
    discovery_attempts = 0
    discovery_insufficient_leads = 0
    for task in report["tasks"]:
        task_id = task["id"]
        leads = task.get("discovery", {}).get("leads", [])
        discovery_ids: tuple[str, ...] = ()
        discovery_status = "not_applicable"
        if task["entry"] != "pair":
            discovery_attempts += 1
            needed = 1 if task["entry"] == "film_first" else 2
            discovery_ids = tuple(f"{task_id}:discovery:{lead['chunk_id']}" for lead in leads[:needed])
            if len(discovery_ids) < needed:
                discovery_insufficient_leads += 1
                discovery_status = "insufficient_leads"
            else:
                selected_discovery.append(discovery_ids)
                discovery_status = ("both_relevant" if all(item in both_relevant for item in discovery_ids)
                                    else "not_both_relevant")
        lenses = task.get("comparison", {}).get("lenses", [])
        focus = next((lens for lens in lenses if lens["identifier"] == "central_question"
                      and lens["first_evidence"] and lens["second_evidence"]), None)
        if focus is None:
            focus = next((lens for lens in lenses if lens["first_evidence"] and lens["second_evidence"]), None)
        pair_ids: tuple[str, ...] = ()
        pair_status = "no_pair"
        if focus is not None:
            pair_ids = tuple(
                f"{task_id}:comparison:{focus['identifier']}:{side}:{focus[f'{side}_evidence']['chunk_id']}"
                for side in ("first", "second")
            )
            focus_pairs.append(pair_ids)
            pair_status = "both_relevant" if all(item in both_relevant for item in pair_ids) else "not_both_relevant"
        task_passages = discovery_ids + pair_ids
        per_task[task_id] = {
            "discovery_status": discovery_status,
            "primary_pair_status": pair_status,
            "selected_passage_ids": list(task_passages),
            "disagreement_passage_ids": [passage_id for passage_id in task_passages
                                          if reviews[0]["passages"][passage_id] != reviews[1]["passages"][passage_id]],
        }
    return {
        "rated_passages": len(expected),
        "both_reviewers_relevant": len(both_relevant),
        "exact_label_agreement": agreement,
        "discovery_attempts": discovery_attempts,
        "discovery_insufficient_leads": discovery_insufficient_leads,
        "selected_discovery_sets": len(selected_discovery),
        "selected_discovery_sets_both_relevant": sum(all(item in both_relevant for item in group)
                                                      for group in selected_discovery),
        "focus_pairs": len(focus_pairs),
        "focus_pairs_both_relevant": sum(all(item in both_relevant for item in pair)
                                         for pair in focus_pairs),
        "per_task": per_task,
    }


def load_tasks(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    tasks = manifest.get("tasks", [])
    if manifest.get("version") != "writer-study-v2" or len(tasks) != 20:
        raise ValueError("Writer study v2 requires exactly 20 frozen tasks.")
    if not isinstance(manifest.get("collection"), str) or not manifest["collection"]:
        raise ValueError("A research collection is required.")
    if Counter(task.get("entry") for task in tasks) != ENTRY_COUNTS:
        raise ValueError("Expected 12 pair, 4 film-first, and 4 question-only tasks.")
    if {task.get("category") for task in tasks} != CATEGORIES:
        raise ValueError("Tasks must cover all eight study categories.")
    ids = [task.get("id") for task in tasks]
    if len(set(ids)) != 20 or any(not isinstance(identifier, str) for identifier in ids):
        raise ValueError("Task IDs must be unique strings.")
    for task in tasks:
        count = {"pair": 2, "film_first": 1, "question_only": 0}[task["entry"]]
        films = task.get("films", [])
        if len(films) != count or len(set(films)) != count or any(
            not isinstance(qid, str) or not qid.startswith("Q") for qid in films
        ):
            raise ValueError(f"{task['id']}: invalid selected film identities.")
        if not isinstance(task.get("question"), str) or not 12 <= len(task["question"]) <= 400:
            raise ValueError(f"{task['id']}: writing question is outside the API contract.")
    return manifest


def run_study(db: Any, manifest: dict[str, Any]) -> dict[str, Any]:
    qids = {qid for task in manifest["tasks"] for qid in task["films"]}
    identities = film_ids(db, collection=manifest["collection"], qids=qids)
    rows = []
    for task in manifest["tasks"]:
        started = perf_counter()
        row: dict[str, Any] = {**task, "status": "not_run"}
        try:
            selected = [identities[qid] for qid in task["films"]]
            if task["entry"] != "pair":
                discovery = discover_films_for_question(
                    ResearchDiscoveryRequest(
                        question=task["question"], exclude_entity_ids=selected, limit=6,
                    ), db=db,
                ).model_dump(mode="json")
                row["discovery"] = discovery
                needed = 1 if task["entry"] == "film_first" else 2
                if len(discovery["leads"]) < needed:
                    row.update({
                        "status": "no_leads",
                        "reason": "Discovery did not return enough source-linked films to form a comparison.",
                    })
                else:
                    selected.extend(lead["film"]["entity_id"] for lead in discovery["leads"][:needed])
            if len(selected) == 2:
                comparison = compare_film_stories(StoryComparisonRequest(
                    first_entity_id=selected[0], second_entity_id=selected[1],
                    question=task["question"],
                ), db=db).model_dump(mode="json")
                row.update({
                    "status": "displayed",
                    "comparison": comparison,
                    "technical_checks": technical_checks(comparison),
                })
        except Exception as exc:
            row.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        row["elapsed_ms"] = round((perf_counter() - started) * 1000, 2)
        rows.append(row)
        print(f"writer study v2: {task['id']} {row['status']} {row['elapsed_ms']} ms", flush=True)
    return {
        "version": manifest["version"],
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "collection": manifest["collection"],
        "run_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "independent_human_review_required",
        "tasks": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture writer study v2 against an isolated local evaluation DB.")
    parser.add_argument("--manifest", type=Path, default=Path("backend/tests/fixtures/writer-study-v2.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/evaluation/writer-study-v2"))
    parser.add_argument("--reviews", nargs=2, type=Path, metavar=("REVIEW_A", "REVIEW_B"))
    args = parser.parse_args()
    if args.reviews:
        report = json.loads((args.output_dir / "study.json").read_text(encoding="utf-8"))
        reviews = [json.loads(path.read_text(encoding="utf-8")) for path in args.reviews]
        summary = aggregate_reviews(report, reviews)
        summary["passage_relevance"] = aggregate_passage_reviews(report, reviews)
        (args.output_dir / "review-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return
    manifest = load_tasks(args.manifest)
    if manifest["collection"] != get_settings().research_collection_code:
        raise ValueError("Study manifest and API research collection must match.")
    with SessionLocal() as db:
        if db.bind.url.database != "cinegraph_eval":
            raise ValueError("Writer study v2 must use the isolated cinegraph_eval database.")
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
