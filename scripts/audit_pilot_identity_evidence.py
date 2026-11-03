"""Read-only provenance audit for IMDb crosslinks in the frozen 100-film pilot."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evaluation = (Path.cwd() / "data/evaluation").resolve()
    if not args.pilot.resolve().is_relative_to(evaluation) or not args.output.resolve().is_relative_to(evaluation):
        raise ValueError("Pilot input and output must remain in local evaluation storage")
    if args.output.exists():
        raise FileExistsError(args.output)
    dsn = os.environ.get("CINEGRAPH_AUDIT_DSN")
    if not dsn:
        raise ValueError("Set CINEGRAPH_AUDIT_DSN to the local cinegraph database")
    settings = conninfo_to_dict(dsn)
    if (settings.get("host") != "127.0.0.1" or settings.get("port", "5432") != "5432"
            or settings.get("dbname") != "cinegraph"):
        raise ValueError("Audit is restricted to local 127.0.0.1:5432/cinegraph")
    raw = args.pilot.read_bytes()
    pilot = json.loads(raw)
    links = []
    for film in pilot["films"]:
        if film["match_status"] != "review_required_unique_imdb_crosslink":
            continue
        if len(film["catalog_candidates"]) != 1:
            raise ValueError(f"Expected one review candidate at rank {film['selection_rank']}")
        candidate = film["catalog_candidates"][0]
        links.append({"selection_rank": film["selection_rank"], "input_title": film["input_title"],
                      "input_year": film["input_year"], "film_id": candidate["film_id"],
                      "catalog_title": candidate["title"], "wikidata_id": candidate["wikidata_id"],
                      "imdb_id": candidate["imdb_id"]})
    results = []
    with psycopg.connect(dsn, hostaddr="127.0.0.1", row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            if conn.execute("SELECT current_database()").fetchone()["current_database"] != "cinegraph":
                raise ValueError("Unexpected catalog database")
            for link in links:
                rows = conn.execute("""SELECT a.id AS assertion_id, a.value_json,
                    a.review_status, ds.name AS data_source, sa.id AS source_assertion_id,
                    sa.source_property, sa.raw_value, sa.extractor_version,
                    ss.source_revision, ss.license, ss.attribution_url,
                    so.canonical_url
                    FROM assertions a
                    JOIN data_sources ds ON ds.id=a.source_id
                    JOIN assertion_evidence ae ON ae.assertion_id=a.id
                    JOIN source_assertions sa ON sa.id=ae.source_assertion_id
                    JOIN source_snapshots ss ON ss.id=sa.source_snapshot_id
                    JOIN source_objects so ON so.id=ss.source_object_id
                    JOIN canonical_entities ce ON ce.id=a.subject_entity_id
                    WHERE ce.wikidata_id=%s AND a.predicate='imdb_identifier'
                      AND a.value_json->>'value'=%s
                    ORDER BY ss.retrieved_at DESC, a.id""",
                    (link["wikidata_id"], link["imdb_id"])).fetchall()
                eligible = [row for row in rows if row["review_status"] == "resolved"
                            and row["data_source"] == "Wikidata" and row["source_property"] == "P345"
                            and row["raw_value"].get("datavalue", {}).get("value") == link["imdb_id"]]
                results.append({**link, "evidence_status": "resolved_wikidata_p345" if eligible else "review_required_missing_exact_p345_evidence",
                    "evidence": [{"assertion_id": str(row["assertion_id"]),
                        "source_assertion_id": str(row["source_assertion_id"]),
                        "source_revision": row["source_revision"], "source_url": row["canonical_url"],
                        "license": row["license"], "attributed": bool(row["attribution_url"]),
                        "review_status": row["review_status"], "source": row["data_source"],
                        "source_property": row["source_property"],
                        "raw_value_matches": row["raw_value"].get("datavalue", {}).get("value") == link["imdb_id"]}
                        for row in rows]})
    report = {"version": "pilot-identity-evidence-v1", "database_read_only": True,
              "pilot_sha256": hashlib.sha256(raw).hexdigest(), "crosslinks": len(results),
              "counts": {status: sum(row["evidence_status"] == status for row in results)
                         for status in sorted({row["evidence_status"] for row in results})},
              "candidates": results,
              "caution": "An exact, sourced P345 identifier supports a cross-source identity candidate; it is not a human approval to merge or publish benchmark-sourced metadata."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"crosslinks": len(results), "counts": report["counts"],
                      "output": str(args.output), "read_only": True}))


if __name__ == "__main__":
    main()
