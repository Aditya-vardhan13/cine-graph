"""Locate old reviewed quotations in new revisions without transferring labels."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import NarrativePassage, SourceSnapshot
from app.services.rag_span_review import bind_review_quotes
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.wikipedia_research import _snapshot_for_qid
from scripts.capture_credit_targets import save_checkpoint
from scripts.capture_writer_identity_recovery import local_output


def locations(quote: str, passages: list[tuple[str, str]]) -> list[dict]:
    if not quote:
        raise ValueError("Empty review quotation")
    found = []
    for passage_id, content in passages:
        offset = 0
        while (start := content.find(quote, offset)) >= 0:
            found.append({"passage_id": passage_id, "start": start, "end": start + len(quote)})
            offset = start + 1
    return found


def whitespace_locations(quote: str, passages: list[tuple[str, str]]) -> list[dict]:
    """Match changed whitespace while retaining exact original passage offsets."""
    words = re.findall(r"\S+", quote)
    if not words:
        raise ValueError("Empty review quotation")
    pattern = re.compile(r"\s+".join(re.escape(word) for word in words))
    return [{"passage_id": passage_id, "start": match.start(), "end": match.end()}
            for passage_id, content in passages for match in pattern.finditer(content)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("review", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    corpus_path, review_path, output = (local_output(path) for path in (args.corpus, args.review, args.output))
    corpus_bytes, review_bytes = corpus_path.read_bytes(), review_path.read_bytes()
    corpus = json.loads(corpus_bytes)
    review = bind_review_quotes(corpus, json.loads(review_bytes))
    documents = {row["chunk_id"]: row for row in corpus["documents"]}
    qids = {evidence["film_qid"] for case in review["cases"] for evidence in case["evidence"]}
    results = []
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        current = {qid: _snapshot_for_qid(db, qid) for qid in qids}
        passages = {}
        for qid, snapshot in current.items():
            if verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size) != "verified":
                raise ValueError(f"Current source bytes failed integrity: {qid}")
            rows = db.scalars(select(NarrativePassage).where(NarrativePassage.source_snapshot_id == snapshot.id)).all()
            if not rows or any(hashlib.sha256(row.content.encode()).hexdigest() != row.content_hash for row in rows):
                raise ValueError(f"Missing or altered current passage: {qid}")
            passages[qid] = [(str(row.id), row.content) for row in rows]
        for case in review["cases"]:
            for evidence in case["evidence"]:
                old_doc = documents[evidence["chunk_id"]]
                old = db.get(SourceSnapshot, UUID(old_doc["source_snapshot_id"]))
                new = current[evidence["film_qid"]]
                if (old is None or old.source_object_id != new.source_object_id
                        or old.content_hash != old_doc["source_content_hash"]
                        or verify_snapshot_file(old.storage_uri, old.content_hash, old.byte_size) != "verified"):
                    raise ValueError(f"Historical source identity or bytes failed: {evidence['film_qid']}")
                found = locations(evidence["quote"], passages[evidence["film_qid"]])
                whitespace_found = [] if found else whitespace_locations(evidence["quote"], passages[evidence["film_qid"]])
                results.append({"case_id": case["case_id"], "film_qid": evidence["film_qid"],
                                "old_snapshot_id": str(old.id), "new_snapshot_id": str(new.id),
                                "old_revision": old.source_revision, "new_revision": new.source_revision,
                                "old_chunk_id": evidence["chunk_id"], "candidates": found,
                                "whitespace_candidates": whitespace_found,
                                "status": "unique" if len(found) == 1 else "missing" if not found else "ambiguous"})
    summary = {name: sum(row["status"] == name for row in results) for name in ("unique", "missing", "ambiguous")}
    report = {"schema": "cinegraph.cross-revision-quote-locations/v2", "status": "review_required",
              "source_corpus_fingerprint": corpus["fingerprint"],
              "review_sha256": hashlib.sha256(review_bytes).hexdigest(),
              "summary": summary, "whitespace_candidates_for_missing": sum(bool(row["whitespace_candidates"]) for row in results),
              "items": results,
              "note": "Exact quote locations across revisions are candidates only, not migrated labels or relevance judgments."}
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing local report")
    save_checkpoint(output, report)
    print(json.dumps({"output": str(output), "summary": summary,
                      "whitespace_candidates_for_missing": report["whitespace_candidates_for_missing"],
                      "status": report["status"]}))


if __name__ == "__main__":
    main()
