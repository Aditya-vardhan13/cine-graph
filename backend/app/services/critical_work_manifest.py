"""Import a human-vetted, metadata-only critical-work manifest.

The importer deliberately does not make network requests. It is the admission
step between source research and any licensed full-text acquisition: each entry
is linked to canonical film identities and stays `metadata_link_only` until an
operator records a compatible licence, access decision, and immutable source
snapshot.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import CanonicalEntity, CriticalWork, CriticalWorkSubject, DataSource


class CriticalManifestError(ValueError):
    pass


def load_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CriticalManifestError(f"Unable to read critical-work manifest: {path}") from exc
    if payload.get("manifest_version") != "critical-pilot-v1" or not isinstance(payload.get("works"), list):
        raise CriticalManifestError("Expected a critical-pilot-v1 manifest with a works array.")
    return payload["works"]


def _require_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CriticalManifestError(f"Expected non-empty string: {key}")
    return value.strip()


def _source_for_entry(db: Session, source_data: dict[str, Any]) -> DataSource:
    name = _require_string(source_data, "name")
    source = db.scalar(select(DataSource).where(DataSource.name == name))
    if source is not None:
        return source
    source = DataSource(
        name=name,
        url=_require_string(source_data, "url"),
        source_type=_require_string(source_data, "source_type"),
        license=_require_string(source_data, "license"),
        rights_status=_require_string(source_data, "rights_status"),
        notes="Registered from a human-vetted critical-work metadata manifest; no content was fetched.",
    )
    db.add(source)
    db.flush()
    return source


def _subjects_for_entry(db: Session, entry: dict[str, Any]) -> list[tuple[CanonicalEntity, str]]:
    subject_data = entry.get("subjects")
    if not isinstance(subject_data, list) or not subject_data:
        raise CriticalManifestError(f"{entry.get('external_id', 'entry')}: needs at least one subject")
    subjects: list[tuple[CanonicalEntity, str]] = []
    for item in subject_data:
        if not isinstance(item, dict):
            raise CriticalManifestError("Each subject must be an object.")
        qid = _require_string(item, "wikidata_id")
        role = _require_string(item, "role")
        if role not in {"primary", "comparison", "context"}:
            raise CriticalManifestError(f"{qid}: invalid subject role {role!r}")
        entity = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == qid))
        if entity is None:
            raise CriticalManifestError(f"{entry.get('external_id', 'entry')}: missing canonical entity {qid}")
        if entity.entity_kind != "film":
            raise CriticalManifestError(f"{qid}: critical-work subject must be a film, got {entity.entity_kind}")
        subjects.append((entity, role))
    return subjects


def import_manifest(db: Session, path: Path) -> dict[str, int]:
    works_created = 0
    works_reused = 0
    subject_links_created = 0
    for entry in load_manifest(path):
        if not isinstance(entry, dict):
            raise CriticalManifestError("Each work must be an object.")
        source_data = entry.get("source")
        if not isinstance(source_data, dict):
            raise CriticalManifestError("Each work needs a source object.")
        source = _source_for_entry(db, source_data)
        external_id = _require_string(entry, "external_id")
        rights_scope = _require_string(entry, "rights_scope")
        if rights_scope != "metadata_link_only":
            raise CriticalManifestError(
                f"{external_id}: this metadata importer accepts only metadata_link_only work; "
                "full text requires an access decision and source snapshot."
            )
        subjects = _subjects_for_entry(db, entry)
        work = db.scalar(select(CriticalWork).where(
            CriticalWork.source_id == source.id,
            CriticalWork.external_id == external_id,
        ))
        if work is None:
            date_value = entry.get("published_on")
            try:
                published_on = date.fromisoformat(date_value) if date_value else None
            except ValueError as exc:
                raise CriticalManifestError(f"{external_id}: published_on must be ISO YYYY-MM-DD") from exc
            authors = entry.get("authors")
            if not isinstance(authors, list) or not all(isinstance(author, str) and author.strip() for author in authors):
                raise CriticalManifestError(f"{external_id}: authors must be a non-empty string list")
            work = CriticalWork(
                source_id=source.id,
                external_id=external_id,
                title=_require_string(entry, "title"),
                canonical_url=_require_string(entry, "canonical_url"),
                authors=[author.strip() for author in authors],
                published_on=published_on,
                work_kind=_require_string(entry, "work_kind"),
                rights_scope=rights_scope,
                work_license=_require_string(entry, "work_license"),
                attribution_text=f"{', '.join(author.strip() for author in authors)} — {source.name}",
                language_code=_require_string(entry, "language_code"),
            )
            db.add(work)
            db.flush()
            works_created += 1
        else:
            works_reused += 1
        existing_links = {
            (link.entity_id, link.subject_role)
            for link in db.scalars(select(CriticalWorkSubject).where(CriticalWorkSubject.critical_work_id == work.id))
        }
        for entity, role in subjects:
            if (entity.id, role) not in existing_links:
                db.add(CriticalWorkSubject(critical_work_id=work.id, entity_id=entity.id, subject_role=role))
                subject_links_created += 1
    db.flush()
    return {
        "works_created": works_created,
        "works_reused": works_reused,
        "subject_links_created": subject_links_created,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import vetted critical-work metadata without fetching article content.")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = import_manifest(db, args.manifest)
        db.commit()
        print({**result, "network_requests": 0})


if __name__ == "__main__":
    main()
