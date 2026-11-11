"""Read-only audit of indexed film/Wikipedia identity and retained source bytes.

This produces review candidates, never identity or rights approvals. Run only
with the local snapshot volume mounted read-only and an explicit output path.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

from sqlalchemy import select, text

from app.db import SessionLocal
from app.models import (CanonicalEntity, DataSource, EvidenceChunk, EvidenceChunkRun, Film,
                        SourceObject, SourceSnapshot)
from app.services.narrative_use_decisions import latest_decisions
from app.services.snapshot_integrity import verify_snapshot_file


def wiki_title(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "en.wikipedia.org" or not parts.path.startswith("/wiki/"):
        return None
    return unquote(parts.path.removeprefix("/wiki/")).replace("_", " ")


def read_snapshot(snapshot: SourceSnapshot) -> dict:
    status = verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size)
    if status != "verified":
        raise ValueError(f"snapshot_integrity_failed:{status}")
    uri = urlsplit(snapshot.storage_uri)
    if uri.scheme != "file" or uri.netloc not in ("", "localhost"):
        raise ValueError("snapshot_uri_not_local")
    payload = json.loads(Path(unquote(uri.path)).read_bytes())
    if not isinstance(payload, dict):
        raise ValueError("snapshot_payload_not_object")
    return payload


def audit(db, run_id: UUID) -> dict:
    run = db.get(EvidenceChunkRun, run_id)
    if run is None or run.status != "complete":
        raise ValueError("A completed, explicit preprocessing run is required.")
    indexed_pairs = select(EvidenceChunk.subject_entity_id.label("entity_id"),
                           EvidenceChunk.source_snapshot_id.label("snapshot_id")).where(
        EvidenceChunk.preprocessing_run_id == run_id, EvidenceChunk.quality_status == "eligible",
    ).distinct().subquery()
    pairs = db.execute(select(CanonicalEntity, Film, SourceObject, SourceSnapshot)
        .join(indexed_pairs, indexed_pairs.c.entity_id == CanonicalEntity.id)
        .outerjoin(Film, Film.entity_id == CanonicalEntity.id)
        .join(SourceSnapshot, SourceSnapshot.id == indexed_pairs.c.snapshot_id)
        .join(SourceObject, SourceObject.id == SourceSnapshot.source_object_id)).all()
    qids = {entity.wikidata_id for entity, _, _, _ in pairs if entity.wikidata_id}
    wiki_source = db.scalar(select(DataSource).where(DataSource.name == "Wikidata"))
    wikidata_rows = [] if wiki_source is None else db.execute(select(SourceObject, SourceSnapshot)
        .join(SourceSnapshot, SourceSnapshot.source_object_id == SourceObject.id)
        .where(SourceObject.source_id == wiki_source.id, SourceObject.external_id.in_(qids),
               SourceSnapshot.fetch_status == "success")
        .order_by(SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc())).all()
    wikidata_by_qid = {}
    for obj, snapshot in wikidata_rows:
        wikidata_by_qid.setdefault(obj.external_id, snapshot)
    decisions = latest_decisions(db, {snapshot.id for _, _, _, snapshot in pairs})
    counters = Counter()
    entries = []
    for entity, film, obj, snapshot in pairs:
        issues = []
        if film is None:
            issues.append("film_profile_missing")
        if not entity.wikidata_id or (film is not None and film.wikidata_id != entity.wikidata_id):
            issues.append("film_wikidata_id_missing_or_conflicting")
        if entity.entity_kind != "film" or entity.lifecycle_status != "active":
            issues.append("entity_not_active_film")
        if snapshot.license != "CC BY-SA 4.0" or not snapshot.attribution_url:
            issues.append("wikipedia_license_or_attribution_missing")
        wikipedia_title = wiki_title(snapshot.canonical_url)
        if wikipedia_title is None or wiki_title(snapshot.attribution_url or "") != wikipedia_title:
            issues.append("wikipedia_url_or_attribution_mismatch")
        try:
            wiki_payload = read_snapshot(snapshot)
            parsed = wiki_payload.get("parse") or {}
            page = wiki_payload.get("page") or {}
            title = parsed.get("title") or page.get("title")
            pageid = parsed.get("pageid") or page.get("pageid")
            revision = parsed.get("revid") or ((page.get("revisions") or [{}])[0]).get("revid")
            if title != wikipedia_title:
                issues.append("wikipedia_payload_title_mismatch")
            if not pageid or obj.external_id != f"enwiki:{pageid}":
                issues.append("wikipedia_page_id_mismatch")
            if not revision or str(revision) != str(snapshot.source_revision):
                issues.append("wikipedia_revision_mismatch")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            issues.append("wikipedia_snapshot_" + ("unavailable" if "snapshot_integrity_failed:missing" in str(exc) else "unreadable_or_invalid"))
        wikidata = wikidata_by_qid.get(entity.wikidata_id)
        if wikidata is None:
            issues.append("wikidata_snapshot_missing")
        else:
            try:
                payload = read_snapshot(wikidata)
                item = payload.get("entities", {}).get(entity.wikidata_id, payload)
                if item.get("id") != entity.wikidata_id:
                    issues.append("wikidata_payload_id_mismatch")
                if (item.get("sitelinks", {}).get("enwiki", {}) or {}).get("title") != wikipedia_title:
                    issues.append("wikidata_sitelink_mismatch")
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                issues.append("wikidata_snapshot_" + ("unavailable" if "snapshot_integrity_failed:missing" in str(exc) else "unreadable_or_invalid"))
        decision = decisions.get(snapshot.id)
        entry = {
            "film_entity_id": str(entity.id), "film_title": entity.canonical_label,
            "wikidata_id": entity.wikidata_id, "wikipedia_snapshot_id": str(snapshot.id),
            "wikipedia_page_id": obj.external_id, "wikipedia_url": snapshot.canonical_url,
            "wikipedia_revision": snapshot.source_revision, "wikipedia_sha256": snapshot.content_hash,
            "wikidata_snapshot_id": str(wikidata.id) if wikidata else None,
            "wikidata_revision": wikidata.source_revision if wikidata else None,
            "wikidata_sha256": wikidata.content_hash if wikidata else None,
            "semantic_use_decision": decision.decision if decision else "unreviewed",
            "identity_status": "review_required", "rights_status": "review_required",
            "mechanical_checks_passed": not issues, "issues": sorted(set(issues)),
        }
        counters["entries"] += 1
        counters["mechanical_pass"] += int(not issues)
        counters[f"decision_{entry['semantic_use_decision']}"] += 1
        for issue in set(issues):
            counters[issue] += 1
        entries.append(entry)
    entries.sort(key=lambda item: (item["film_title"].casefold(), item["wikipedia_snapshot_id"]))
    return {"schema": "cinegraph.writer-source-identity-audit/v1", "chunk_run_id": str(run.id),
            "collection_code": run.collection_code, "review_status": "review_required",
            "scope_note": "Mechanical consistency only; no identity or rights approval is recorded.",
            "counts": dict(counters), "entries": entries}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-run-id", type=UUID, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        report = audit(db, args.chunk_run_id)
    data = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite an existing audit report")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(json.dumps({"output": str(args.output), "sha256": sha256(data).hexdigest(), "counts": report["counts"]}))


if __name__ == "__main__":
    main()
