"""Read-only pilot export with exact provenance and separate question splits."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def split_cases(design):
    facets = design["facets"]
    if len(set(facets)) != len(facets):
        raise ValueError("duplicate_facets")
    result = {"development": [], "question_holdout": []}
    seen_pairs, seen_ids = set(), set()
    for pair in design["pairs"]:
        key = tuple(sorted(pair["films"]))
        if len(key) != 2 or key[0] == key[1] or key in seen_pairs or pair["id"] in seen_ids:
            raise ValueError("duplicate_or_invalid_pair")
        seen_pairs.add(key)
        seen_ids.add(pair["id"])
        if len(pair["questions"]) != len(facets) or pair["split"] not in result:
            raise ValueError("invalid_questions_or_split")
        for facet, question in zip(facets, pair["questions"], strict=True):
            result[pair["split"]].append({
                "case_id": pair["id"]+"."+facet, "film_qids": pair["films"],
                "question": question, "requested_facet": facet,
                "source_labels_status": "pending",
                "discovery_urls": pair["discovery_urls"],
            })
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--design", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--holdout-output", type=Path, required=True)
    args = p.parse_args()
    if args.output.resolve() == args.holdout_output.resolve():
        raise ValueError("split_outputs_must_differ")
    if args.output.exists() or args.holdout_output.exists():
        raise FileExistsError("export_already_exists")
    raw = args.design.read_bytes()
    design = json.loads(raw)
    cases = split_cases(design)
    qids = {q for pair in design["pairs"] for q in pair["films"]}
    from sqlalchemy import select, text
    from app.db import SessionLocal
    from app.models import Film
    from app.services.current_narrative_passages import current_passage_rows
    from app.services.narrative_use_decisions import latest_decisions
    from app.services.source_rights_policy import can_use_narrative_semantically
    from app.services.snapshot_integrity import verify_snapshot_file
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        films = list(db.scalars(select(Film).where(Film.wikidata_id.in_(qids))))
        if len(films) != len(qids) or {f.wikidata_id for f in films} != qids:
            raise ValueError("missing_or_ambiguous_pilot_identity")
        by_id = {f.entity_id: f for f in films}
        rows = current_passage_rows(db, set(by_id))
        snapshots = {s.id: s for _, s in rows}
        decisions = latest_decisions(db, set(snapshots))
        eligible, excluded = set(), []
        for sid, s in snapshots.items():
            d = decisions.get(sid)
            if not d or not can_use_narrative_semantically(
                decision=d.decision, basis_url=d.decision_basis_url, notes=d.decision_notes,
                license_name=s.license, attribution_url=s.attribution_url):
                excluded.append({"snapshot_id": str(sid), "reason": "semantic_use_not_approved"})
                continue
            if verify_snapshot_file(s.storage_uri, s.content_hash, s.byte_size) != "verified":
                raise ValueError("approved_snapshot_integrity_failed:"+str(sid))
            eligible.add(sid)
        documents = []
        for passage, snapshot in rows:
            if snapshot.id not in eligible:
                continue
            if hashlib.sha256(passage.content.encode()).hexdigest() != passage.content_hash:
                raise ValueError("passage_hash_mismatch")
            film = by_id[passage.subject_entity_id]
            documents.append({"chunk_id": str(passage.id), "film_qid": film.wikidata_id,
                "film_title": film.canonical_title, "entity_id": str(film.entity_id),
                "section_title": passage.section_title, "section_locator": passage.section_locator,
                "passage_ordinal": passage.ordinal, "source_snapshot_id": str(snapshot.id),
                "source_url": snapshot.canonical_url, "source_revision": snapshot.source_revision,
                "source_sha256": snapshot.content_hash, "source_license": snapshot.license,
                "attribution_url": snapshot.attribution_url, "content": passage.content,
                "content_sha256": passage.content_hash, "extraction_version": passage.extraction_version,
                "decision_version": decisions[snapshot.id].decision_version})
        if {d["film_qid"] for d in documents} != qids:
            raise ValueError("pilot_film_lacks_eligible_current_text")
        documents.sort(key=lambda d: (d["film_qid"], d["section_locator"],
                                     d["passage_ordinal"], d["chunk_id"]))
    corpus = {"schema": "cinegraph.recovery-pilot-corpus/v1",
        "question_design_sha256": hashlib.sha256(raw).hexdigest(),
        "independent_gold": False, "documents": documents,
        "excluded_sources": sorted(excluded, key=lambda s: s["snapshot_id"]),
        "cases": cases["development"]}
    corpus["fingerprint"] = fingerprint(corpus)
    holdout = {"schema": "cinegraph.recovery-question-holdout/v1",
        "source_corpus_fingerprint": corpus["fingerprint"], "independent_gold": False,
        "film_disjoint": False, "cases": cases["question_holdout"]}
    holdout["fingerprint"] = fingerprint(holdout)
    for path, value in ((args.output, corpus), (args.holdout_output, holdout)):
        with path.open("x") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
    print(json.dumps({"films":len(qids),"documents":len(documents),
        "development_questions":len(corpus["cases"]), "heldout_questions":len(holdout["cases"]),
        "corpus_fingerprint":corpus["fingerprint"], "heldout_fingerprint":holdout["fingerprint"]}))


if __name__ == "__main__":
    main()
