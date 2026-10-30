"""Read-only comparison of restricted and whole-film retrieval on local evaluation data.

This diagnoses candidate visibility, not answer relevance. It never queries the
working corpus or changes the live API route. Run against ``cinegraph_eval``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from app.models import CanonicalEntity
from app.services.hybrid_evidence_retrieval import (
    NarrativeRetrievalMethod, embed_narrative_queries, retrieve_narrative_candidates,
)
from app.services.retrieval_scope import resolve_retrieval_scope
from app.services.story_comparison import focus_evidence_question_id


def manifest_cases(manifest: dict, *, pair_count: int) -> list[tuple[str, str, str, str]]:
    """Use the frozen manifest order; never select examples after seeing rankings."""
    pairs = manifest.get("pairs", [])
    if not 1 <= pair_count <= len(pairs):
        raise ValueError("pair_count must select one or more complete manifest pairs.")
    cases = []
    for pair in pairs[:pair_count]:
        if len(pair["films"]) != 2 or len(pair["questions"]) != 5:
            raise ValueError("Each selected pair must contain two films and five questions.")
        for number, question in enumerate(pair["questions"], start=1):
            cases.append((f"{pair['id']}-Q{number}", pair["films"][0], pair["films"][1], question))
    return cases


def run_canary(
    db: Session, manifest: dict, *, pair_count: int = 4,
    method: NarrativeRetrievalMethod = NarrativeRetrievalMethod.LEXICAL,
    collection_code: str | None = None,
) -> dict:
    cases = manifest_cases(manifest, pair_count=pair_count)
    selected_collection = collection_code or manifest["collection"]
    if selected_collection not in {manifest["collection"], "english-10-parser-canary-v2"}:
        raise ValueError("The section canary accepts only the frozen baseline or v2 canary collection.")
    scope = resolve_retrieval_scope(db, collection_code=selected_collection)
    embedding_started = perf_counter()
    vectors = (
        embed_narrative_queries(db, question_texts=[case[3] for case in cases], scope=scope)
        if method in {NarrativeRetrievalMethod.HYBRID, NarrativeRetrievalMethod.SEMANTIC}
        else (None,) * len(cases)
    )
    embedding_batch_ms = round((perf_counter() - embedding_started) * 1000, 2)
    qids = {qid for _, first, second, _ in cases for qid in (first, second)}
    entities = {
        entity.wikidata_id: entity.id
        for entity in db.scalars(select(CanonicalEntity).where(CanonicalEntity.wikidata_id.in_(qids)))
    }
    if set(entities) != qids:
        raise ValueError(f"Evaluation corpus is missing film IDs: {sorted(qids - set(entities))}")
    results = []
    ranking_ms = 0.0
    for (case_id, first, second, question), vector in zip(cases, vectors, strict=True):
        sides = []
        for qid in (first, second):
            request = dict(
                subject_entity_id=entities[qid],
                question_id=focus_evidence_question_id(question),
                question_text=question,
                method=method,
                scope=scope,
                query_vector=vector,
                limit=10,
                candidate_limit=30,
            )
            restricted = retrieve_narrative_candidates(db, **request)
            whole_film = retrieve_narrative_candidates(db, restrict_sections=False, **request)
            ranking_ms += restricted.database_ranking_milliseconds + whole_film.database_ranking_milliseconds
            restricted_ids = {item.chunk_id for item in restricted.evidence}
            new_evidence = [item for item in whole_film.evidence if item.chunk_id not in restricted_ids]
            def review_options(result):
                return [{
                    "chunk_id": item.chunk_id,
                    "source_snapshot_id": item.source_snapshot_id,
                    "section_locator": item.section_locator,
                    "content": item.content,
                    "matched_by": item.matched_by,
                } for item in result.evidence[:3]]
            sides.append({
                "film_qid": qid,
                "question_route": request["question_id"],
                "restricted_candidates": len(restricted.evidence),
                "whole_film_candidates": len(whole_film.evidence),
                "new_candidate_ids": [item.chunk_id for item in new_evidence],
                "new_candidate_sections": [item.section_locator for item in new_evidence],
                "restricted_top_three": review_options(restricted),
                "whole_film_top_three": review_options(whole_film),
            })
        results.append({"case_id": case_id, "question": question, "sides": sides})
    return {
        "manifest_version": manifest["version"],
        "collection_code": selected_collection,
        "chunk_run_id": str(scope.preprocessing_run_id),
        "index_run_id": str(scope.index_run.id) if scope.index_run is not None else None,
        "method": method.value,
        "query_embedding_batch_ms": embedding_batch_ms,
        "database_ranking_total_ms": round(ranking_ms, 2),
        "comparison": "restricted-vs-whole-film",
        "case_count": len(results),
        "sides_with_new_candidates": sum(bool(side["new_candidate_ids"]) for row in results for side in row["sides"]),
        "results": results,
        "caution": "Visibility is not relevance; unchanged or expanded candidates do not prove better answers.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--method", choices=[item.value for item in NarrativeRetrievalMethod], default="lexical")
    parser.add_argument("--collection", help="Frozen baseline or isolated parser-v2 ten-film collection")
    parser.add_argument("--output", type=Path, help="Optional ignored local report under data/evaluation")
    args = parser.parse_args()
    if make_url(args.database_url).database != "cinegraph_eval":
        raise ValueError("The section canary may run only against cinegraph_eval.")
    report_root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    output_path = args.output.resolve() if args.output is not None else None
    if output_path is not None and not output_path.is_relative_to(report_root):
        raise ValueError("Reports must stay under this project's ignored data/evaluation directory.")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            report = run_canary(
                db, manifest, pair_count=args.pairs, method=NarrativeRetrievalMethod(args.method),
                collection_code=args.collection,
            )
    finally:
        engine.dispose()
    output = json.dumps(report, indent=2)
    if output_path is None:
        print(output)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
        print(json.dumps({key: report[key] for key in (
            "collection_code", "chunk_run_id", "index_run_id", "method", "case_count",
            "sides_with_new_candidates", "query_embedding_batch_ms", "database_ranking_total_ms", "caution",
        )}, indent=2))


if __name__ == "__main__":
    main()
