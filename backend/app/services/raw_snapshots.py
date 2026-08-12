"""Immutable local snapshot storage used by permitted source adapters.

Production storage may be S3-compatible object storage. The database stores a
content-addressed URI either way, so parsing can be reproduced without making
another request to the source.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DataSource, RawIngestionRun, RawIngestionRunSnapshot, SourceAssertion, SourceObject, SourceSnapshot


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def store_payload(source_id: UUID, payload: bytes, suffix: str = ".json") -> tuple[str, str]:
    """Write once by content hash and return a portable file URI and hash."""
    digest = sha256(payload)
    root = Path(get_settings().raw_snapshot_root).expanduser().resolve()
    target = root / str(source_id) / digest[:2] / f"{digest}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(payload)
    return target.as_uri(), digest


def source_object(
    db: Session,
    *,
    source: DataSource,
    external_id: str,
    object_kind: str,
    canonical_url: str,
) -> SourceObject:
    item = db.scalar(select(SourceObject).where(
        SourceObject.source_id == source.id,
        SourceObject.external_id == external_id,
    ))
    if item:
        return item
    item = SourceObject(
        source_id=source.id,
        external_id=external_id,
        object_kind=object_kind,
        canonical_url=canonical_url,
    )
    db.add(item)
    db.flush()
    return item


def snapshot(
    db: Session,
    *,
    item: SourceObject,
    run: RawIngestionRun,
    payload: bytes,
    source_revision: str | None,
    canonical_url: str,
    license: str,
    attribution_url: str | None,
    media_type: str = "application/json",
    parser_version: str | None = None,
) -> tuple[SourceSnapshot, bool]:
    storage_uri, content_hash = store_payload(item.source_id, payload)
    existing = db.scalar(select(SourceSnapshot).where(
        SourceSnapshot.source_object_id == item.id,
        SourceSnapshot.source_revision == source_revision,
        SourceSnapshot.content_hash == content_hash,
    ))
    if existing:
        link_snapshot_to_run(db, run.id, existing.id, "reused")
        return existing, False
    created = SourceSnapshot(
        source_object_id=item.id,
        ingestion_run_id=run.id,
        source_revision=source_revision,
        canonical_url=canonical_url,
        http_status=200,
        media_type=media_type,
        content_hash=content_hash,
        byte_size=len(payload),
        storage_uri=storage_uri,
        license=license,
        attribution_url=attribution_url,
        parser_version=parser_version,
    )
    db.add(created)
    db.flush()
    link_snapshot_to_run(db, run.id, created.id, "created")
    return created, True


def link_snapshot_to_run(db: Session, run_id: UUID, snapshot_id: UUID, disposition: str) -> None:
    exists = db.scalar(select(RawIngestionRunSnapshot.id).where(
        RawIngestionRunSnapshot.ingestion_run_id == run_id,
        RawIngestionRunSnapshot.source_snapshot_id == snapshot_id,
    ))
    if not exists:
        db.add(RawIngestionRunSnapshot(
            ingestion_run_id=run_id, source_snapshot_id=snapshot_id, disposition=disposition,
        ))


def source_assertion(
    db: Session,
    *,
    source_snapshot_id: UUID,
    statement_locator: str,
    source_property: str | None,
    raw_subject: dict,
    raw_value: dict,
    raw_qualifiers: dict,
    source_rank: str | None,
    extractor_version: str,
) -> bool:
    exists = db.scalar(select(SourceAssertion.id).where(
        SourceAssertion.source_snapshot_id == source_snapshot_id,
        SourceAssertion.statement_locator == statement_locator,
        SourceAssertion.extractor_version == extractor_version,
    ))
    if exists:
        return False
    db.add(SourceAssertion(
        source_snapshot_id=source_snapshot_id,
        statement_locator=statement_locator,
        source_property=source_property,
        raw_subject=raw_subject,
        raw_value=raw_value,
        raw_qualifiers=raw_qualifiers,
        source_rank=source_rank,
        extractor_version=extractor_version,
    ))
    return True
