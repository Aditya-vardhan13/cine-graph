"""Read-only, source-linked comparison capture for a frozen 10-pair study.

This is a *review packet*, not an automatic claim of answer relevance. The
questions are versioned in Git; retrieved passages and reviewer labels stay
local. Run only against the isolated cinegraph_eval database.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

from sqlalchemy import select, text
from sqlalchemy.engine.url import make_url

from app.db import SessionLocal, settings
from app.models import CanonicalEntity
from app.services.hybrid_evidence_retrieval import (
    NarrativeRetrievalMethod, embed_narrative_queries, retrieve_narrative_candidates,
)
from app.services.ollama_embeddings import OllamaEmbeddingClient
from app.services.retrieval_scope import resolve_retrieval_scope
from app.services.story_comparison import compare_story_evidence, focus_evidence_question_id


def validate_manifest(manifest: dict) -> None:
    pairs = manifest.get("pairs", [])
    if len(pairs) != 10 or len({pair["id"] for pair in pairs}) != 10:
        raise ValueError("The relevance study requires ten distinct film pairs.")
    if any(len(pair["films"]) != 2 or len(pair["questions"]) != 5 for pair in pairs):
        raise ValueError("Each pair requires two film IDs and five questions.")
    if len({question for pair in pairs for question in pair["questions"]}) != 50:
        raise ValueError("The fifty writing questions must be distinct.")


def merge_candidate_captures(*captures: dict) -> dict:
    """Union candidate pools from complete captures of the same frozen study.

    This preserves the first capture's order for stable baseline display, adds
    unseen chunks from later retrieval methods, and fails closed if a repeated
    chunk ID no longer points to the same source passage.
    """
    if len(captures) < 2:
        raise ValueError("Candidate union requires at least two captures.")
    methods = [capture.get("method") for capture in captures]
    if any(not method for method in methods) or len(set(methods)) != len(methods):
        raise ValueError("Candidate captures must have distinct retrieval methods.")
    indexed = []
    for capture in captures:
        cases = capture.get("cases", [])
        if len(cases) != 50:
            raise ValueError("Candidate union requires complete 50-case captures.")
        by_id = {case["case_id"]: case for case in cases}
        if len(by_id) != 50:
            raise ValueError("Candidate capture contains duplicate or missing case IDs.")
        indexed.append(by_id)

    base = captures[0]
    base_ids = set(indexed[0])
    for capture, cases in zip(captures[1:], indexed[1:], strict=True):
        if set(cases) != base_ids or capture.get("manifest_version") != base.get("manifest_version"):
            raise ValueError("Candidate captures must use the same frozen questions.")
        for case_id in base_ids:
            original = indexed[0][case_id]
            added = cases[case_id]
            stable_fields = ("pair_id", "film_qids", "titles", "question")
            if any(original.get(field) != added.get(field) for field in stable_fields):
                raise ValueError(f"Candidate captures disagree about {case_id}.")

    merged_cases = []
    stable_source_fields = (
        "content", "subject_entity_id", "source_snapshot_id", "section_locator",
        "section_title", "source_url", "source_revision", "source_license",
    )
    for case_id, original in indexed[0].items():
        merged = deepcopy(original)
        for side in ("first", "second"):
            pool_by_id: dict[str, dict] = {}
            source_by_id: dict[str, list[str]] = {}
            for method, case_map in zip(methods, indexed, strict=True):
                for item in case_map[case_id][f"{side}_pool"]:
                    chunk_id = item["chunk_id"]
                    previous = pool_by_id.get(chunk_id)
                    if previous is not None:
                        if any(previous.get(field) != item.get(field)
                               for field in stable_source_fields):
                            raise ValueError(f"Source passage changed for chunk {chunk_id}.")
                    else:
                        pool_by_id[chunk_id] = deepcopy(item)
                        source_by_id[chunk_id] = []
                    source_by_id[chunk_id].append(method)
            merged[f"{side}_pool"] = []
            for item in pool_by_id.values():
                item["retrieval_sources"] = source_by_id[item["chunk_id"]]
                merged[f"{side}_pool"].append(item)
        merged_cases.append(merged)
    return {
        "manifest_version": base.get("manifest_version"),
        "method": "candidate-union",
        "source_methods": methods,
        "cases": merged_cases,
    }


def require_isolated_database() -> None:
    if make_url(settings.database_url).database != "cinegraph_eval":
        raise RuntimeError("Pair relevance evaluation may run only against cinegraph_eval.")


def validate_retrieval_candidate_limit(candidate_limit: int) -> None:
    if not 10 <= candidate_limit <= 200:
        raise ValueError("Retrieval candidate limit must be between 10 and 200.")


def capture(
    manifest: dict,
    method: NarrativeRetrievalMethod,
    *,
    retrieval_candidate_limit: int = 30,
) -> dict:
    validate_manifest(manifest)
    validate_retrieval_candidate_limit(retrieval_candidate_limit)
    require_isolated_database()
    qids = {qid for pair in manifest["pairs"] for qid in pair["films"]}
    records = []
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        ids = dict(db.execute(select(CanonicalEntity.wikidata_id, CanonicalEntity.id).where(
            CanonicalEntity.wikidata_id.in_(qids),
        )).all())
        if qids - ids.keys():
            raise ValueError(f"Films missing from evaluation DB: {sorted(qids - ids.keys())}")
        scope = resolve_retrieval_scope(db, collection_code=manifest["collection"])
        client = OllamaEmbeddingClient(base_url=settings.ollama_base_url)
        for pair in manifest["pairs"]:
            for ordinal, question in enumerate(pair["questions"], start=1):
                started = perf_counter()
                result = compare_story_evidence(
                    db,
                    first_entity_id=ids[pair["films"][0]],
                    second_entity_id=ids[pair["films"][1]],
                    question=question,
                    requested_method=method,
                    embedding_client=client,
                    collection_code=manifest["collection"],
                )
                if result.degraded:
                    raise RuntimeError(f"{pair['id']}-Q{ordinal}: hybrid retrieval degraded: {result.fallback_reason}")
                focus = next((lens for lens in result.lenses if lens.identifier == "central_question"), None)
                query_vector = (
                    embed_narrative_queries(db, question_texts=[question], client=client, scope=scope)[0]
                    if method == NarrativeRetrievalMethod.HYBRID else None
                )
                pool = [retrieve_narrative_candidates(
                    db, subject_entity_id=ids[qid],
                    question_id=focus_evidence_question_id(question), question_text=question,
                    method=method, limit=10, candidate_limit=retrieval_candidate_limit,
                    client=client, query_vector=query_vector, scope=scope,
                ) for qid in pair["films"]]
                records.append({
                    "case_id": f"{pair['id']}-Q{ordinal}",
                    "pair_id": pair["id"],
                    "film_qids": pair["films"],
                    "titles": pair["titles"],
                    "question": question,
                    "answerability_status": result.answerability_status,
                    "answerability_reason": result.answerability_reason,
                    "retrieval_method": result.retrieval_method,
                    "degraded": result.degraded,
                    "fallback_reason": result.fallback_reason,
                    "preprocessing_run_id": result.preprocessing_run_id,
                    "index_run_id": result.index_run_id,
                    "elapsed_ms": round((perf_counter() - started) * 1000, 1),
                    "first_options": [asdict(item) for item in pool[0].evidence[:3]],
                    "second_options": [asdict(item) for item in pool[1].evidence[:3]],
                    "first_pool": [asdict(item) for item in pool[0].evidence],
                    "second_pool": [asdict(item) for item in pool[1].evidence],
                    "other_lenses": [
                        {"identifier": lens.identifier,
                         "first_chunk_id": lens.first_evidence.chunk_id if lens.first_evidence else None,
                         "second_chunk_id": lens.second_evidence.chunk_id if lens.second_evidence else None}
                        for lens in result.lenses if lens.identifier != "central_question"
                    ],
                })
                print(f"{len(records):02d}/50 {records[-1]['case_id']} {result.answerability_status}", flush=True)
    return {"manifest_version": manifest["version"], "method": method.value, "cases": records}


def score(capture_data: dict, labels: dict, *, reranking: dict | None = None) -> dict:
    """Compute conservative pair success only from externally reviewed labels.

    A side is relevant when its first displayed passage is labeled relevant.
    A pair succeeds only when *both* first passages are relevant. Missing
    labels fail closed instead of silently becoming irrelevant.
    """
    cases = capture_data["cases"]
    if len(cases) != 50:
        raise ValueError("The full 50-case capture is required for a score.")
    ranked_cases = validate_reranking(capture_data, reranking) if reranking else {}
    outcome = []
    for case in cases:
        sides = []
        for side, qid in zip(("first", "second"), case["film_qids"], strict=True):
            options = (ranked_cases[case["case_id"]][f"{side}_ranking"] if reranking
                       else case[f"{side}_options"])
            first = options[0] if options else None
            key = f"{case['case_id']}|{qid}|{first['chunk_id'] if first else 'NONE'}"
            if key not in labels or labels[key] not in (0, 1):
                raise ValueError(f"Missing 0/1 source-relevance label: {key}")
            sides.append(labels[key])
        outcome.append({"case_id": case["case_id"], "first": sides[0], "second": sides[1],
                        "pair_success": int(all(sides))})
    return {
        "cases": len(outcome),
        "side_precision_at_1": round(sum(row["first"] + row["second"] for row in outcome) / 100, 3),
        "pair_success_at_1": round(sum(row["pair_success"] for row in outcome) / 50, 3),
        "passed_80_percent_pair_gate": sum(row["pair_success"] for row in outcome) >= 40,
        "per_case": outcome,
    }


def validate_reranking(capture_data: dict, reranking: dict) -> dict[str, dict]:
    """Reject a stale or truncated ranking before comparing model outcomes."""
    cases = capture_data["cases"]
    ranked_cases = {case["case_id"]: case for case in reranking["cases"]}
    if (not reranking.get("complete") or len(reranking["cases"]) != len(cases)
            or set(ranked_cases) != {case["case_id"] for case in cases}):
        raise ValueError("A reranker score requires the same complete 50-case capture.")
    for case in cases:
        ranked = ranked_cases[case["case_id"]]
        if ranked["question"] != case["question"] or ranked["film_qids"] != case["film_qids"]:
            raise ValueError(f"Reranker question/films differ for {case['case_id']}.")
        for side in ("first", "second"):
            original = [item["chunk_id"] for item in case[f"{side}_pool"]]
            reranked = [item["chunk_id"] for item in ranked[f"{side}_ranking"]]
            if len(original) != len(reranked) or set(original) != set(reranked):
                raise ValueError(f"Reranker candidate pool differs for {case['case_id']} {side}.")
    return ranked_cases


def reciprocal_rank_fusion(capture_data: dict, rankings: list[dict], *, constant: int = 60) -> dict:
    """Fuse complete rankings over the same captured candidate pools.

    This is an offline evaluation primitive, not a new production retrieval
    path. Rank fusion avoids assuming that scores from different models share
    a calibrated scale. Stable chunk-ID tie breaking makes the trial repeatable.
    """
    if not rankings or constant < 1:
        raise ValueError("Rank fusion requires at least one ranking and a positive constant.")
    validated = [validate_reranking(capture_data, ranking) for ranking in rankings]
    cases = []
    for case in capture_data["cases"]:
        row = {"case_id": case["case_id"], "question": case["question"],
               "film_qids": case["film_qids"]}
        for side in ("first", "second"):
            scores = {item["chunk_id"]: 0.0 for item in case[f"{side}_pool"]}
            for model in validated:
                for rank, item in enumerate(model[case["case_id"]][f"{side}_ranking"], start=1):
                    scores[item["chunk_id"]] += 1 / (constant + rank)
            row[f"{side}_ranking"] = [
                {"chunk_id": chunk_id, "score": round(score, 8)}
                for chunk_id, score in sorted(scores.items(), key=lambda entry: (-entry[1], entry[0]))
            ]
        cases.append(row)
    return {"model": "reciprocal-rank-fusion", "complete": True, "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", choices=("hybrid", "lexical", "semantic"), default="hybrid")
    parser.add_argument("--retrieval-candidate-limit", type=int, default=30,
                        help="Pool size searched before returning each film-side top ten (10-200).")
    parser.add_argument("--labels", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = capture(
        manifest,
        NarrativeRetrievalMethod(args.method),
        retrieval_candidate_limit=args.retrieval_candidate_limit,
    )
    if args.labels:
        result["reviewed_metrics"] = score(result, json.loads(args.labels.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cases": len(result["cases"]),
                      "reviewed_metrics": result.get("reviewed_metrics")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
