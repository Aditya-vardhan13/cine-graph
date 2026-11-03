"""Read-only catalog overlap audit; creates local review candidates, never database records."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.external_catalog_identity_audit import match_summary_identity


def validate_local_dsn(dsn: str) -> None:
    settings = conninfo_to_dict(dsn)
    if (settings.get("host") != "127.0.0.1" or settings.get("port", "5432") != "5432"
            or settings.get("dbname") != "cinegraph" or settings.get("service")
            or settings.get("hostaddr", "127.0.0.1") != "127.0.0.1"):
        raise ValueError("Audit access is restricted to the local project catalog on 127.0.0.1:5432.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prepared", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    local = (ROOT / "data/evaluation").resolve()
    if not local.is_relative_to(ROOT.resolve()) or any(not p.resolve().is_relative_to(local) for p in (args.prepared, args.output)):
        raise ValueError("Input and output must be local evaluation paths.")
    if args.output.exists():
        raise FileExistsError("Existing review output must not be overwritten.")
    report = json.loads((args.prepared / "report.json").read_text())
    raw = (args.prepared / "evidence-documents.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest() != report["outputs"]["evidence-documents"]["sha256"]:
        raise ValueError("Prepared source fingerprint mismatch.")
    docs = [row for row in map(json.loads, raw.splitlines()) if row["dataset"] == "narrative-similarity"]
    ids = sorted({i.get("wikidata_id") for d in docs for i in d["identities"] if i.get("wikidata_id")})
    # Connection string is supplied through a dedicated local environment variable;
    # it is never printed or written to the review artifact.
    dsn = os.environ.get("CINEGRAPH_AUDIT_DSN")
    if not dsn:
        raise ValueError("Set CINEGRAPH_AUDIT_DSN to the local catalog's read-only connection.")
    validate_local_dsn(dsn)
    # Explicit hostaddr also overrides any inherited PGHOSTADDR environment setting.
    with psycopg.connect(dsn, hostaddr="127.0.0.1", row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            name = conn.execute("SELECT current_database()").fetchone()["current_database"]
            if name != "cinegraph":
                raise ValueError("This read-only catalog audit expects the cinegraph database.")
            films = conn.execute("SELECT id, wikidata_id, canonical_title, review_status FROM films WHERE wikidata_id = ANY(%s)", (ids,)).fetchall()
    catalog_by_qid = {f["wikidata_id"]: f for f in films}
    candidates = [match_summary_identity(doc, catalog_by_qid) for doc in docs]
    output = {"version": "external-catalog-overlap-v1", "read_only": True,
              "prepared_documents_sha256": report["outputs"]["evidence-documents"]["sha256"],
              "counts": dict(Counter(row["match_status"] for row in candidates)), "candidates": candidates,
              "caution": "QID matches are unreviewed candidates, not source facts or approved product evidence; source text may already exist."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as f:
        json.dump(output, f, indent=2)
    print(json.dumps({"source_documents": len(docs), "counts": output["counts"], "read_only": True}))


if __name__ == "__main__":
    main()
