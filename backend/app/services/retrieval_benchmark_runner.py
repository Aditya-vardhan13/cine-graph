"""Run the evidence-linked benchmark against local persisted retrieval lanes."""
from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    Assertion,
    CanonicalEntity,
    EvidenceChunk,
    Film,
    NarrativePassage,
    ReferenceCollectionMembership,
    SourceSnapshot,
)
from app.services.hybrid_evidence_retrieval import (
    NarrativeRetrievalMethod,
    _active_index,
    retrieve_narrative_candidates,
)
from app.services.ollama_embeddings import OllamaEmbeddingClient, OllamaEmbeddingProfile
from app.services.retrieval_benchmark import (
    BenchmarkCase,
    BenchmarkTarget,
    acceptance_gate,
    aggregate_benchmark_metrics,
    grouped_ranking_metrics,
    grouped_scoped_ranking_metrics,
    load_benchmark,
)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def _entity_ids(db: Session, qids: set[str]) -> dict[str, UUID]:
    values = dict(db.execute(select(CanonicalEntity.wikidata_id, CanonicalEntity.id).where(
        CanonicalEntity.wikidata_id.in_(qids)
    )).all())
    missing = qids - values.keys()
    if missing:
        raise ValueError(f"Benchmark QIDs are missing from canonical entities: {sorted(missing)}")
    return values


def _narrative_target_ids(
    db: Session,
    *,
    target: BenchmarkTarget,
    chunk_run_id: UUID,
) -> set[str]:
    rows = db.scalars(
        select(EvidenceChunk.id)
        .join(NarrativePassage, NarrativePassage.id == EvidenceChunk.narrative_passage_id)
        .join(CanonicalEntity, CanonicalEntity.id == NarrativePassage.subject_entity_id)
        .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
        .where(
            CanonicalEntity.wikidata_id == target.subject_qid,
            SourceSnapshot.source_revision == target.source_revision,
            NarrativePassage.section_locator == target.section_locator,
            NarrativePassage.content_hash == target.content_hash,
            EvidenceChunk.preprocessing_run_id == chunk_run_id,
            EvidenceChunk.quality_status == "eligible",
        )
    ).all()
    return {str(identifier) for identifier in rows}


def _assertion_target_ids(db: Session, *, target: BenchmarkTarget) -> set[str]:
    statement = (
        select(Assertion.id)
        .join(CanonicalEntity, CanonicalEntity.id == Assertion.subject_entity_id)
        .where(
            CanonicalEntity.wikidata_id == target.subject_qid,
            Assertion.predicate == target.predicate,
            Assertion.review_status.in_(("resolved", "published")),
        )
    )
    if target.object_qid:
        statement = statement.where(Assertion.object_entity.has(CanonicalEntity.wikidata_id == target.object_qid))
    if target.source_revision:
        statement = statement.where(Assertion.source_revision == target.source_revision)
    return {str(identifier) for identifier in db.scalars(statement).all()}


def _target_groups(
    db: Session,
    *,
    case: BenchmarkCase,
    chunk_run_id: UUID,
) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = defaultdict(set)
    for target in case.targets:
        identifiers = (
            _narrative_target_ids(db, target=target, chunk_run_id=chunk_run_id)
            if target.kind == "narrative_passage"
            else _assertion_target_ids(db, target=target)
        )
        if not identifiers:
            raise ValueError(f"{case.case_id}: target fingerprint no longer resolves for {target.group}")
        groups[target.group].update(identifiers)
    return dict(groups)


def _structured_ranking(db: Session, *, case: BenchmarkCase, entity_ids: dict[str, UUID]) -> list[str]:
    predicate = case.targets[0].predicate
    return [str(identifier) for identifier in db.scalars(
        select(Assertion.id).where(
            Assertion.subject_entity_id == entity_ids[case.subject_qids[0]],
            Assertion.predicate == predicate,
            Assertion.review_status.in_(("published", "resolved")),
        ).order_by(
            (Assertion.review_status == "published").desc(),
            Assertion.created_at.desc(),
            Assertion.id,
        )
    ).all()]


def _coverage(db: Session, *, collection_code: str) -> dict[str, Any]:
    membership_filter = (
        ReferenceCollectionMembership.collection_code == collection_code,
        ReferenceCollectionMembership.status == "included",
    )
    total = db.scalar(select(func.count(distinct(ReferenceCollectionMembership.entity_id))).where(*membership_filter)) or 0
    film_projection = db.scalar(
        select(func.count(distinct(ReferenceCollectionMembership.entity_id)))
        .join(Film, Film.entity_id == ReferenceCollectionMembership.entity_id)
        .where(*membership_filter)
    ) or 0
    reviewed_assertions = db.scalar(
        select(func.count(distinct(ReferenceCollectionMembership.entity_id)))
        .join(Assertion, Assertion.subject_entity_id == ReferenceCollectionMembership.entity_id)
        .where(*membership_filter, Assertion.review_status.in_(("resolved", "published")))
    ) or 0
    return {
        "collection_entities": total,
        "film_projection_entities": film_projection,
        "reviewed_assertion_entities": reviewed_assertions,
        "film_projection_percent": round(film_projection / total * 100, 2) if total else 0.0,
        "reviewed_assertion_percent": round(reviewed_assertions / total * 100, 2) if total else 0.0,
        "gate": "informational_known_debt",
    }


def _embed_questions(
    cases: list[BenchmarkCase],
    *,
    profile: OllamaEmbeddingProfile,
    client: OllamaEmbeddingClient,
    batch_size: int,
) -> tuple[dict[str, list[float]], float]:
    started = perf_counter()
    vectors: dict[str, list[float]] = {}
    for offset in range(0, len(cases), batch_size):
        batch = cases[offset: offset + batch_size]
        embedded = client.embed([profile.query_input(case.question_text) for case in batch], profile=profile)
        vectors.update((case.case_id, vector) for case, vector in zip(batch, embedded, strict=True))
        print(f"benchmark embeddings: {min(offset + len(batch), len(cases))}/{len(cases)}", flush=True)
    return vectors, (perf_counter() - started) * 1000


def run_benchmark(
    db: Session,
    *,
    manifest_path: Path,
    split: str,
    model_name: str,
    collection_code: str,
    cutoff: int = 10,
    candidate_limit: int = 50,
    batch_size: int = 24,
    client: OllamaEmbeddingClient | None = None,
) -> dict[str, Any]:
    benchmark = load_benchmark(manifest_path)
    cases = [case for case in benchmark.cases if split == "all" or case.split == split]
    if not cases:
        raise ValueError(f"No benchmark cases for split {split!r}")
    qids = {qid for case in cases for qid in case.subject_qids}
    entity_ids = _entity_ids(db, qids)
    index_run, model = _active_index(db, model_name=model_name)
    target_groups_by_case = {
        case.case_id: _target_groups(db, case=case, chunk_run_id=index_run.evidence_chunk_run_id)
        for case in cases
    }
    narrative_cases = [case for case in cases if case.evidence_class == "narrative_extraction"]
    embedding_client = client or OllamaEmbeddingClient()
    profile = OllamaEmbeddingProfile(
        model=model.model_name, dimensions=model.dimension, query_instruction=model.query_instruction,
    )
    vectors, embedding_ms = _embed_questions(
        narrative_cases, profile=profile, client=embedding_client, batch_size=batch_size,
    )
    method_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    database_latencies: dict[str, list[float]] = defaultdict(list)
    provenance_results = 0
    provenance_complete = 0

    for position, case in enumerate(cases, start=1):
        relevant_groups = target_groups_by_case[case.case_id]
        if case.evidence_class == "source_fact":
            ranking = _structured_ranking(db, case=case, entity_ids=entity_ids)
            metrics = grouped_ranking_metrics(ranking, relevant_groups, cutoff=cutoff)
            row = {"case_id": case.case_id, "category": case.category, "question": case.question_text, **metrics}
            method_rows["structured"].append(row)
            method_rows["system"].append(row)
            provenance_results += len(ranking[:cutoff])
            if ranking:
                provenance_complete += db.scalar(select(func.count()).select_from(Assertion).where(
                    Assertion.id.in_([UUID(value) for value in ranking[:cutoff]]),
                    Assertion.source_reference.is_not(None),
                )) or 0
        else:
            for method in NarrativeRetrievalMethod:
                rankings_by_group: dict[str, list[str]] = {}
                for qid in case.subject_qids:
                    result = retrieve_narrative_candidates(
                        db,
                        subject_entity_id=entity_ids[qid],
                        question_id=case.question_id,
                        question_text=case.question_text,
                        evidence_class=case.evidence_class,
                        method=method,
                        limit=cutoff,
                        candidate_limit=candidate_limit,
                        model_name=model_name,
                        query_vector=vectors[case.case_id] if method != NarrativeRetrievalMethod.LEXICAL else None,
                    )
                    rankings_by_group[qid] = [item.chunk_id for item in result.evidence]
                    database_latencies[method.value].append(result.database_ranking_milliseconds)
                    if method == NarrativeRetrievalMethod.HYBRID:
                        provenance_results += len(result.evidence)
                        provenance_complete += sum(bool(item.source_snapshot_id) for item in result.evidence)
                metrics = grouped_scoped_ranking_metrics(rankings_by_group, relevant_groups, cutoff=cutoff)
                row = {"case_id": case.case_id, "category": case.category, "question": case.question_text, **metrics}
                method_rows[method.value].append(row)
                if method == NarrativeRetrievalMethod.HYBRID:
                    method_rows["system"].append(row)
        print(f"benchmark cases: {position}/{len(cases)}", flush=True)

    metrics = {method: aggregate_benchmark_metrics(rows, cutoff=cutoff) for method, rows in method_rows.items()}
    system_gate = acceptance_gate(metrics["system"], cutoff=cutoff)
    return {
        "benchmark_version": benchmark.version,
        "adjudication_status": benchmark.adjudication_status,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "split": split,
        "case_count": len(cases),
        "model": {"provider": model.provider, "name": model.model_name, "revision": model.model_revision, "dimension": model.dimension},
        "index": {"run_id": str(index_run.id), "chunk_run_id": str(index_run.evidence_chunk_run_id), "chunks": index_run.chunks_completed},
        "retrieval": {"cutoff": cutoff, "candidate_limit": candidate_limit, "hybrid_fusion": "weighted_rrf_k60_semantic3_lexical1"},
        "metrics": metrics,
        "acceptance_gate": system_gate,
        "provenance": {
            "retrieved_results": provenance_results,
            "results_with_source_pointer": provenance_complete,
            "coverage": round(provenance_complete / provenance_results, 4) if provenance_results else 0.0,
        },
        "catalog_coverage": _coverage(db, collection_code=collection_code),
        "latency_milliseconds": {
            "batched_query_embedding_total": round(embedding_ms, 3),
            "batched_query_embedding_each": round(embedding_ms / len(narrative_cases), 3) if narrative_cases else 0.0,
            "database_p50": {method: round(median(values), 3) for method, values in database_latencies.items()},
            "database_p95": {method: round(_percentile(values, 0.95), 3) for method, values in database_latencies.items()},
        },
        "failures": [
            row for row in method_rows["system"]
            if row["complete_case_recall"] == 0 or row["mean_reciprocal_rank"] < 0.5
        ],
    }


def write_html_report(report: dict[str, Any], output: Path) -> None:
    overall = report["metrics"]["system"]["overall"]
    categories = report["metrics"]["system"]["by_category"]
    methods = report["metrics"]
    cutoff = report["retrieval"]["cutoff"]
    def percentage(value: float) -> str:
        return f"{value * 100:.1f}%"
    category_rows = "".join(
        f"<tr><td>{html.escape(name.replace('_', ' ').title())}</td>"
        f"<td>{values['cases']}</td><td>{percentage(values[f'target_group_recall_at_{cutoff}'])}</td>"
        f"<td>{percentage(values[f'complete_case_recall_at_{cutoff}'])}</td>"
        f"<td>{values[f'mrr_at_{cutoff}']:.3f}</td></tr>"
        for name, values in categories.items()
    )
    method_rows = "".join(
        f"<tr><td>{html.escape(name)}</td><td>{values['overall']['cases']}</td>"
        f"<td>{percentage(values['overall'][f'target_group_recall_at_{cutoff}'])}</td>"
        f"<td>{values['overall'][f'mrr_at_{cutoff}']:.3f}</td></tr>"
        for name, values in methods.items()
    )
    failure_rows = "".join(
        f"<tr><td>{html.escape(row['case_id'])}</td><td>{html.escape(row['question'])}</td>"
        f"<td>{html.escape(json.dumps(row['first_relevant_ranks'], sort_keys=True))}</td></tr>"
        for row in report["failures"]
    ) or "<tr><td colspan='3'>No low-ranked or missed cases.</td></tr>"
    coverage = report["catalog_coverage"]
    document = f"""<!doctype html><html><head><meta charset='utf-8'><title>CineGraph retrieval benchmark</title>
<style>body{{font:15px system-ui;background:#0b0d12;color:#e8ecf5;margin:0;padding:32px}}main{{max-width:1100px;margin:auto}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}}.card,table{{background:#151924;border:1px solid #2a3142;border-radius:12px}}.card{{padding:18px}}.value{{font-size:30px;color:#84f3cf}}table{{width:100%;border-collapse:collapse;margin:14px 0 30px}}th,td{{padding:11px;text-align:left;border-bottom:1px solid #2a3142}}th{{color:#8fa0ba}}.warn{{color:#ffcc70}}code{{color:#a8b8ff}}</style></head><body><main>
<h1>CineGraph retrieval benchmark</h1><p><code>{html.escape(report['benchmark_version'])}</code> · {html.escape(report['split'])} split · {report['case_count']} cases</p>
<div class='grid'><div class='card'><div>Target recall@{cutoff}</div><div class='value'>{percentage(overall[f'target_group_recall_at_{cutoff}'])}</div></div>
<div class='card'><div>Complete case recall@{cutoff}</div><div class='value'>{percentage(overall[f'complete_case_recall_at_{cutoff}'])}</div></div>
<div class='card'><div>MRR@{cutoff}</div><div class='value'>{overall[f'mrr_at_{cutoff}']:.3f}</div></div>
<div class='card'><div>Evidence provenance</div><div class='value'>{percentage(report['provenance']['coverage'])}</div></div></div>
<h2>System quality by category</h2><table><thead><tr><th>Category</th><th>Cases</th><th>Target recall</th><th>Complete cases</th><th>MRR</th></tr></thead><tbody>{category_rows}</tbody></table>
<h2>Retrieval method comparison</h2><table><thead><tr><th>Method</th><th>Cases</th><th>Target recall</th><th>MRR</th></tr></thead><tbody>{method_rows}</tbody></table>
<h2>Known catalog debt</h2><p class='warn'>The narrative collection has {coverage['collection_entities']} entities; {coverage['film_projection_entities']} ({coverage['film_projection_percent']}%) currently have legacy Film projection rows and {coverage['reviewed_assertion_entities']} ({coverage['reviewed_assertion_percent']}%) have reviewed assertions. This is reported, not hidden by semantic retrieval.</p>
<h2>Cases needing attention</h2><table><thead><tr><th>Case</th><th>Question</th><th>First evidence rank</th></tr></thead><tbody>{failure_rows}</tbody></table>
</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate local CineGraph retrieval against benchmark v1.")
    parser.add_argument("--manifest", default="backend/tests/fixtures/retrieval-benchmark-v1.json")
    parser.add_argument("--split", choices=("development", "test", "all"), default="development")
    parser.add_argument("--model", default="qwen3-embedding:0.6b")
    parser.add_argument("--collection", default="english-1000-retained-narrative-v1")
    parser.add_argument("--cutoff", type=int, default=10)
    parser.add_argument("--candidate-limit", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=24)
    parser.add_argument("--output-dir", default="data/evaluation/retrieval-benchmark-v1")
    arguments = parser.parse_args()
    with SessionLocal() as db:
        report = run_benchmark(
            db, manifest_path=Path(arguments.manifest), split=arguments.split, model_name=arguments.model,
            collection_code=arguments.collection, cutoff=arguments.cutoff,
            candidate_limit=arguments.candidate_limit, batch_size=arguments.batch_size,
        )
    output_dir = Path(arguments.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_output = output_dir / f"{arguments.split}.json"
    html_output = output_dir / f"{arguments.split}.html"
    json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    write_html_report(report, html_output)
    print(json.dumps({
        "json": str(json_output), "html": str(html_output),
        "metrics": report["metrics"]["system"]["overall"], "gate": report["acceptance_gate"],
    }, indent=2))


if __name__ == "__main__":
    main()
