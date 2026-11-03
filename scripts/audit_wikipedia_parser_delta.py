"""Compare two Wikipedia parsers on retained snapshots without changing the corpus.

Run inside the project API container with its raw-snapshot volume mounted. The
report is a review queue, not an automatic decision to promote either parser.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections import defaultdict
import hashlib
import json
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models import CanonicalEntity, NarrativePassage, SourceSnapshot
from app.services.wikipedia_passages_v2 import derive_passages as derive_v2
from app.services.wikipedia_research import _snapshot_payload, snapshot_wikitext
from app.services.wikipedia_text_v3 import derive_passages as derive_v3


def compare_passages(old, new):
    """Compare source locators; a shifted key is not automatically lost text."""
    def keyed(passages):
        result = {(p.section_locator, p.ordinal): p.content for p in passages}
        if len(result) != len(passages):
            raise ValueError("Duplicate passage locator and ordinal")
        return result

    a, b = keyed(old), keyed(new)
    common = a.keys() & b.keys()
    changed = [key for key in common if a[key] != b[key]]
    def section_text(passages):
        sections = defaultdict(list)
        for passage in passages:
            sections[passage.section_locator].append((passage.ordinal, passage.content))
        return {locator: "".join("".join(value.split()) for _, value in sorted(parts))
                for locator, parts in sections.items()}

    def is_subsequence(needle, haystack):
        iterator = iter(haystack)
        return all(any(character == candidate for candidate in iterator) for character in needle)

    old_sections, new_sections = section_text(old), section_text(new)
    suspicious = sorted(locator for locator, value in old_sections.items()
                        if not is_subsequence(value, new_sections.get(locator, "")))
    return {
        "old_passages": len(a), "new_passages": len(b),
        "changed_shared_keys": len(changed),
        "old_only_keys": len(a.keys() - b.keys()),
        "new_only_keys": len(b.keys() - a.keys()),
        "changed_locators": sorted({key[0] for key in changed}),
        "sections_with_possible_v2_text_loss": suspicious,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0, help="Optional film limit; zero means all recovered films")
    args = parser.parse_args()
    dburl = make_url(args.database_url)
    if dburl.database != "cinegraph" or dburl.host not in {"db", "127.0.0.1", "localhost"}:
        raise ValueError("Only the local project corpus may be audited")
    if args.limit < 0 or args.output.exists():
        raise ValueError("Limit must be nonnegative and output must not already exist")
    root = Path("/workspace/data/evaluation").resolve()
    if not args.output.resolve().is_relative_to(root):
        raise ValueError("Output must be inside the project evaluation directory")
    engine = create_engine(args.database_url)
    results = []
    errors = []
    try:
        with Session(engine) as db:
            db.execute(text("SET TRANSACTION READ ONLY"))
            if db.execute(text("SELECT current_database()")).scalar_one() != "cinegraph":
                raise ValueError("Unexpected database")
            query = (select(CanonicalEntity.wikidata_id, CanonicalEntity.canonical_label, SourceSnapshot)
                     .join(NarrativePassage, NarrativePassage.subject_entity_id == CanonicalEntity.id)
                     .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
                     .where(NarrativePassage.extraction_version == "enwiki-section-passages-recovered-v1")
                     .order_by(CanonicalEntity.wikidata_id, SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc())
                     .distinct(CanonicalEntity.wikidata_id))
            if args.limit:
                query = query.limit(args.limit)
            for qid, title, snapshot in db.execute(query):
                try:
                    if snapshot.license != "CC BY-SA 4.0" or not snapshot.attribution_url:
                        raise ValueError("Snapshot attribution or license not eligible")
                    wikitext, source_title, _ = snapshot_wikitext(_snapshot_payload(snapshot))
                    delta = compare_passages(derive_v2(wikitext), derive_v3(wikitext))
                    results.append({"qid": qid, "title": title, "source_title": source_title,
                                    "snapshot_id": str(snapshot.id), "source_revision": snapshot.source_revision,
                                    "snapshot_sha256": snapshot.content_hash, **delta})
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    errors.append({"qid": qid, "snapshot_id": str(snapshot.id),
                                   "error_type": type(exc).__name__, "error": str(exc)})
    finally:
        engine.dispose()
    counts = Counter("changed" if row["changed_shared_keys"] or row["old_only_keys"] or row["new_only_keys"]
                     else "unchanged" for row in results)
    report = {"version": "wikipedia-parser-delta-v2", "database_read_only": True,
              "selection": "latest recovered-v1 passage snapshot per film", "limit": args.limit,
              "counts": dict(counts), "errors": errors, "films": results,
              "caution": "Key and whitespace-insensitive subsequence checks are review leads; passing does not prove preservation, improvement, or retrieval accuracy."}
    payload = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as out:
        out.write(payload)
    print(json.dumps({"films": len(results), "counts": dict(counts), "errors": len(errors),
                      "report_sha256": hashlib.sha256(payload).hexdigest()}))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
