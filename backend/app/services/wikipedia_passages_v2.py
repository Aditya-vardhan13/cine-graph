"""Materialise parser-v2 derivatives from immutable, attributed snapshots.

The CLI is deliberately limited to the isolated evaluation database while the
ten-film canary is reviewed. Existing v1 passages are never updated or deleted.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session

from app.models import (
    CanonicalEntity, NarrativePassage, ReferenceCollection, ReferenceCollectionMembership, SourceSnapshot,
)
from app.services.wikipedia_research import (
    _snapshot_payload, citation_markers, snapshot_wikitext, split_sections,
)
from app.services.wikipedia_text_v2 import EXTRACTION_VERSION, chunk_section_v2, readable_wikitext


CANARY_COLLECTION = "english-10-parser-canary-v2"


@dataclass(frozen=True)
class DerivedPassage:
    section_locator: str
    section_title: str
    ordinal: int
    content: str
    citation_markers: tuple[str, ...]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


def derive_passages(wikitext: str) -> list[DerivedPassage]:
    """Keep image captions distinct from article prose under stable locators."""
    passages = []
    next_ordinal: dict[str, int] = {}
    for section in split_sections(wikitext):
        locator = str(section["locator"])
        title = str(section["title"])
        for raw in chunk_section_v2(str(section["content"])):
            parsed = readable_wikitext(raw)
            if parsed.text:
                ordinal = next_ordinal.get(locator, 0)
                passages.append(DerivedPassage(
                    locator, title, ordinal, parsed.text, tuple(citation_markers(raw)),
                ))
                next_ordinal[locator] = ordinal + 1
            for caption in parsed.media_captions:
                caption_locator = f"{locator}/media-caption"
                caption_ordinal = next_ordinal.get(caption_locator, 0)
                passages.append(DerivedPassage(
                    caption_locator, f"{title} / Image caption",
                    caption_ordinal, caption, (),
                ))
                next_ordinal[caption_locator] = caption_ordinal + 1
    return passages


def materialise_passages(
    db: Session, *, entity_id: UUID, snapshot: SourceSnapshot, wikitext: str,
) -> dict[str, int]:
    """Append one versioned derivative set; reject drift for a pinned revision."""
    if snapshot.license != "CC BY-SA 4.0" or not snapshot.attribution_url:
        raise ValueError("Narrative extraction requires attributable CC BY-SA source material.")
    prepared = derive_passages(wikitext)
    existing_rows = list(db.scalars(select(NarrativePassage).where(
        NarrativePassage.source_snapshot_id == snapshot.id,
        NarrativePassage.extraction_version == EXTRACTION_VERSION,
    )))
    existing = {
        (passage.section_locator, passage.ordinal, passage.content_hash): passage
        for passage in existing_rows
    }
    prepared_keys = {(item.section_locator, item.ordinal, item.content_hash) for item in prepared}
    if len(prepared_keys) != len(prepared) or len(existing) != len(existing_rows):
        raise ValueError("Duplicate source passage identity in v2 derivation.")
    if any(key not in prepared_keys or passage.subject_entity_id != entity_id
           for key, passage in existing.items()):
        raise ValueError("Pinned source revision disagrees with an existing v2 derivative.")
    created = 0
    for item in prepared:
        key = (item.section_locator, item.ordinal, item.content_hash)
        if key in existing:
            continue
        db.add(NarrativePassage(
            subject_entity_id=entity_id,
            source_snapshot_id=snapshot.id,
            section_locator=item.section_locator,
            section_title=item.section_title,
            ordinal=item.ordinal,
            content=item.content,
            content_hash=item.content_hash,
            citation_markers=list(item.citation_markers),
            extraction_version=EXTRACTION_VERSION,
        ))
        created += 1
    return {"prepared": len(prepared), "created": created, "reused": len(prepared) - created}


def ensure_canary_collection(db: Session, *, qids: list[str], manifest_version: str) -> None:
    """Pin exactly ten reviewed-film identities in an eval-only collection."""
    entities = {
        entity.wikidata_id: entity.id
        for entity in db.scalars(select(CanonicalEntity).where(CanonicalEntity.wikidata_id.in_(qids)))
    }
    if set(entities) != set(qids):
        raise ValueError("The ten-film canary includes a missing canonical film.")
    collection = db.get(ReferenceCollection, CANARY_COLLECTION)
    if collection is None:
        db.add(ReferenceCollection(
            code=CANARY_COLLECTION, title="English parser v2 ten-film canary",
            description="Isolated first-five-pair extraction and retrieval trial; not a live catalog.",
            language_code="en", selection_method="frozen-dev-manifest-first-five-pairs",
            selection_version=manifest_version,
        ))
        db.flush()
    elif collection.selection_version != manifest_version:
        raise ValueError("Existing canary collection uses a different manifest version.")
    existing = {
        member.entity_id
        for member in db.scalars(select(ReferenceCollectionMembership).where(
            ReferenceCollectionMembership.collection_code == CANARY_COLLECTION,
        ))
    }
    expected = set(entities.values())
    if existing and existing != expected:
        raise ValueError("Existing canary membership does not match the frozen ten-film set.")
    if not existing:
        db.add_all(ReferenceCollectionMembership(
            collection_code=CANARY_COLLECTION,
            entity_id=entities[qid], selection_position=position,
            selection_signals={"wikidata_id": qid},
            source_reference="project:backend/tests/fixtures/pair-relevance-50-v1.json",
        ) for position, qid in enumerate(qids, start=1))
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--write-eval", action="store_true", help="Append v2 rows in cinegraph_eval only")
    parser.add_argument("--build-chunks", action="store_true", help="Build an isolated v2 chunk run after extraction")
    args = parser.parse_args()
    if make_url(args.database_url).database != "cinegraph_eval":
        raise ValueError("The v2 canary may materialise only into cinegraph_eval.")
    if not args.write_eval:
        raise ValueError("Pass --write-eval to append v2 derivatives in cinegraph_eval.")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    qids = [qid for pair in manifest["pairs"][:5] for qid in pair["films"]]
    if len(qids) != 10 or len(set(qids)) != 10:
        raise ValueError("The canary requires exactly ten distinct film IDs.")
    engine = create_engine(args.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as db:
            rows = db.execute(
                select(CanonicalEntity.wikidata_id, CanonicalEntity.id, SourceSnapshot)
                .join(NarrativePassage, NarrativePassage.subject_entity_id == CanonicalEntity.id)
                .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
                .where(CanonicalEntity.wikidata_id.in_(qids), SourceSnapshot.fetch_status == "success")
                .order_by(CanonicalEntity.wikidata_id, SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc())
                .distinct(CanonicalEntity.wikidata_id)
            ).all()
            by_qid = {qid: (entity_id, snapshot) for qid, entity_id, snapshot in rows}
            if set(by_qid) != set(qids):
                raise ValueError(f"Missing retained source revisions for {sorted(set(qids) - set(by_qid))}")
            results = []
            for qid in qids:
                entity_id, snapshot = by_qid[qid]
                payload = _snapshot_payload(snapshot)
                wikitext, _, _ = snapshot_wikitext(payload)
                counts = materialise_passages(db, entity_id=entity_id, snapshot=snapshot, wikitext=wikitext)
                db.commit()
                results.append({"qid": qid, "snapshot_id": str(snapshot.id), **counts})
            chunk_report = None
            if args.build_chunks:
                # Chunking imports spaCy; extraction alone should not need it.
                from app.services.evidence_preprocessing import ChunkConfiguration, build_evidence_chunks
                ensure_canary_collection(db, qids=qids, manifest_version=manifest["version"])
                chunk_report = build_evidence_chunks(
                    db, collection_code=CANARY_COLLECTION,
                    config=ChunkConfiguration(extraction_version=EXTRACTION_VERSION),
                )
    finally:
        engine.dispose()
    print(json.dumps({
        "extraction_version": EXTRACTION_VERSION, "films": results,
        "chunk_run": chunk_report,
    }, indent=2))


if __name__ == "__main__":
    main()
