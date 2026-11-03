"""Read-only overlap indicators for exact-QID candidates; no source publication."""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from audit_external_catalog_overlap import validate_local_dsn
from app.services.source_overlap_audit import source_coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    local = (ROOT / "data/evaluation").resolve()
    if not local.is_relative_to(ROOT.resolve()) or any(not p.resolve().is_relative_to(local) for p in (args.prepared, args.candidates, args.output)):
        raise ValueError("Inputs and output must stay under project evaluation storage.")
    if args.output.exists():
        raise FileExistsError("Existing reports cannot be overwritten.")
    candidates_raw = args.candidates.read_bytes()
    candidates = json.loads(candidates_raw)
    report = json.loads((args.prepared / "report.json").read_text())
    raw = (args.prepared / "evidence-documents.jsonl").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != report["outputs"]["evidence-documents"]["sha256"] or digest != candidates["prepared_documents_sha256"]:
        raise ValueError("Candidate and source fingerprints disagree.")
    selected = [r for r in candidates["candidates"] if r["match_status"] == "exact_qid_candidate"]
    docids = {r["document_id"] for r in selected}
    docs = {r["document_id"]: r for r in map(json.loads, raw.splitlines()) if r["document_id"] in docids}
    if set(docs) != docids:
        raise ValueError("Candidate document is missing.")
    dsn = os.environ.get("CINEGRAPH_AUDIT_DSN")
    if not dsn:
        raise ValueError("Set CINEGRAPH_AUDIT_DSN for the local catalog.")
    validate_local_dsn(dsn)
    with psycopg.connect(dsn, hostaddr="127.0.0.1", row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            if conn.execute("SELECT current_database()").fetchone()["current_database"] != "cinegraph":
                raise ValueError("Expected the local cinegraph catalog.")
            rows = conn.execute("""SELECT f.id AS film_id, f.wikidata_id, n.source_snapshot_id,
                n.section_title, n.section_locator, n.ordinal, n.content,
                s.canonical_url, s.source_revision, s.license
                FROM films f JOIN narrative_passages n ON n.subject_entity_id=f.entity_id
                JOIN source_snapshots s ON s.id=n.source_snapshot_id
                WHERE f.id = ANY(%s::uuid[]) ORDER BY f.id, n.source_snapshot_id, n.section_locator, n.ordinal""",
                ([c["catalog_film_id"] for c in selected],)).fetchall()
    byfilm = defaultdict(list)
    for row in rows:
        byfilm[str(row["film_id"])].append(row)
    results = []
    for candidate in selected:
        sources = defaultdict(list)
        for row in byfilm[candidate["catalog_film_id"]]:
            if row["wikidata_id"] not in candidate["source_qids"]:
                raise ValueError("Catalog identity changed since the candidate audit.")
            if "plot" in row["section_title"].casefold():
                sources[str(row["source_snapshot_id"])].append(row)
        comparisons = []
        for snapshot_id, passages in sources.items():
            text = "\n".join(p["content"] for p in passages)
            first = passages[0]
            comparisons.append({"source_snapshot_id": snapshot_id, "source_url": first["canonical_url"],
                "source_revision": first["source_revision"], "license": first["license"],
                "passages": len(passages), **source_coverage(docs[candidate["document_id"]]["content"], text)})
        results.append({"document_id": candidate["document_id"], "catalog_film_id": candidate["catalog_film_id"],
                        "catalog_title": candidate["catalog_title"], "source_qids": candidate["source_qids"],
                        "total_existing_passages": len(byfilm[candidate["catalog_film_id"]]),
                        "plot_snapshot_comparisons": comparisons, "review_status": "review_required"})
    output = {"version": "external-passage-overlap-v1", "candidate_file_sha256": hashlib.sha256(candidates_raw).hexdigest(),
        "prepared_documents_sha256": digest, "read_only": True, "items": results,
        "caution": "Five-word lexical overlap only; zero or high overlap does not prove novelty, duplication, rights, or relevance."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        json.dump(output, f, indent=2)
    print(json.dumps({"candidates": len(results), "with_existing_plot": sum(bool(r["plot_snapshot_comparisons"]) for r in results),
                      "read_only": True}))


if __name__ == "__main__":
    main()
