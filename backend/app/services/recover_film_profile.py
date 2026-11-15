"""Explicitly stage a missing film profile from a retained Wikidata snapshot.

This creates review-required projections, never an automatically published film.
The caller owns the transaction and must provide the exact reviewed identity.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (Assertion, AssertionEvidence, CanonicalEntity, DataSource, Film, FilmProvenance,
                        LanguageEdition, SourceAssertion, SourceObject, SourceSnapshot)
from app.services.research_metadata import language_code_for_qids
from app.services.snapshot_integrity import verify_snapshot_file
from app.services.wikidata_raw import entity_from_entitydata


def stage_missing_profile(db: Session, *, qid: str, snapshot_id: UUID, snapshot_hash: str,
                          expected_title: str, expected_language: str, reviewer: str, review_note: str) -> Film:
    if not re.fullmatch(r"Q[1-9][0-9]*", qid) or len(reviewer.strip()) < 3 or len(review_note.strip()) < 20:
        raise ValueError("Explicit identity review is required")
    entity = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == qid).with_for_update())
    if not entity or entity.entity_kind != "film" or entity.lifecycle_status != "active":
        raise ValueError("Expected an existing active film entity")
    if db.scalar(select(Film.id).where((Film.entity_id == entity.id) | (Film.wikidata_id == qid))):
        raise ValueError("Film profile already exists")
    row = db.execute(select(SourceSnapshot, SourceObject, DataSource).join(
        SourceObject, SourceObject.id == SourceSnapshot.source_object_id).join(
        DataSource, DataSource.id == SourceObject.source_id).where(SourceSnapshot.id == snapshot_id)).first()
    if not row:
        raise ValueError("Source snapshot not found")
    snapshot, obj, source = row
    latest = db.scalar(select(SourceSnapshot.id).where(SourceSnapshot.source_object_id == obj.id,
        SourceSnapshot.fetch_status == "success").order_by(SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc()).limit(1))
    if (source.name != "Wikidata" or obj.external_id != qid or snapshot.id != latest
            or snapshot.content_hash != snapshot_hash or snapshot.license != "CC0 1.0"
            or verify_snapshot_file(snapshot.storage_uri, snapshot.content_hash, snapshot.byte_size) != "verified"):
        raise ValueError("Snapshot identity, currency, rights or integrity mismatch")
    payload = json.loads(Path(unquote(urlsplit(snapshot.storage_uri).path)).read_bytes())
    item = entity_from_entitydata(payload, qid)
    if str(item.get("lastrevid")) != str(snapshot.source_revision):
        raise ValueError("Snapshot revision mismatch")
    title = ((item.get("labels") or {}).get("en") or {}).get("value")
    if not isinstance(title, str) or title != expected_title or not title.strip():
        raise ValueError("Reviewed title does not match retained source")
    claims = item.get("claims") or {}
    selected: dict[str, tuple[str, dict]] = {"wikidata:label:en": ("labels.en", {"language": "en", "text": title})}
    for prop in ("P31", "P364"):
        statements = claims.get(prop) or []
        valid = [(i, statement.get("mainsnak")) for i, statement in enumerate(statements)
                 if statement.get("mainsnak", {}).get("snaktype") == "value"]
        if len(valid) != 1:
            raise ValueError(f"Expected exactly one unambiguous {prop} statement")
        index, value = valid[0]
        selected[prop] = (f"claims.{prop}[{index}]", value)
    def item_id(value: dict) -> str | None:
        return ((value.get("datavalue") or {}).get("value") or {}).get("id")
    if item_id(selected["P31"][1]) != "Q11424":
        raise ValueError("Retained source does not identify a film")
    language_qid = item_id(selected["P364"][1])
    language = language_code_for_qids({language_qid} if language_qid else set())
    if language in {"und", "mul"} or language != expected_language or not db.get(LanguageEdition, language):
        raise ValueError("Reviewed original language is missing or ambiguous")
    raw_rows = {}
    for prop, (locator, expected_value) in selected.items():
        matches = list(db.scalars(select(SourceAssertion).where(
            SourceAssertion.source_snapshot_id == snapshot.id, SourceAssertion.statement_locator == locator,
            SourceAssertion.source_property == prop)))
        matches = [raw for raw in matches if raw.raw_value == expected_value and raw.raw_subject.get("wikidata_id") == qid]
        if len(matches) != 1 or db.scalar(select(AssertionEvidence.id).where(AssertionEvidence.source_assertion_id == matches[0].id)):
            raise ValueError(f"Source assertion {locator} missing, ambiguous or already projected")
        raw_rows[prop] = matches[0]
    film = Film(entity_id=entity.id, wikidata_id=qid, canonical_title=title,
                original_language_code=language, country_codes=[], review_status="review_required")
    db.add(film)
    db.flush()
    for prop, predicate, value in (("wikidata:label:en", "canonical_title", {"text": title, "language": "en"}),
                                   ("P31", "instance_of", {"wikidata_id": "Q11424"}),
                                   ("P364", "original_language", {"wikidata_id": language_qid})):
        raw = raw_rows[prop]
        reference = f"{snapshot.canonical_url}#{raw.statement_locator}"
        assertion = Assertion(subject_entity_id=entity.id, predicate=predicate, source_property=prop,
                              value_json=value, source_id=source.id, source_reference=snapshot.canonical_url,
                              source_revision=snapshot.source_revision, assertion_kind="source_fact",
                              derivation_version="reviewed-profile-recovery-v1", review_status="review_required",
                              qualifiers={"reviewer": reviewer.strip(), "review_note": review_note.strip()})
        db.add(assertion)
        db.add(AssertionEvidence(assertion=assertion, source_assertion_id=raw.id, evidence_type="source_assertion",
                                 reference=reference, note="Explicit profile identity review; not published."))
        if prop in {"wikidata:label:en", "P364"}:
            db.add(FilmProvenance(film_id=film.id, source_id=source.id,
                                  field_name="canonical_title" if prop == "wikidata:label:en" else "original_language_code",
                                  source_reference=reference))
    db.flush()
    return film
