"""Attributable credit read model; source statements stay source-specific."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assertion, CanonicalEntity, DataSource, SourceAssertion, SourceObject, SourceSnapshot
from app.services.source_rights_policy import displayable_rights_statuses


@dataclass(frozen=True)
class SourcedCredit:
    name: str
    role: str
    character_name: str | None
    position: int | None
    source_url: str
    name_source_url: str | None = None
    name_source_revision: str | None = None
    character_source_url: str | None = None
    character_source_revision: str | None = None


@dataclass(frozen=True)
class SourcedCreditGroup:
    source_name: str
    source_license: str
    rights_status: str
    credits: tuple[SourcedCredit, ...]


def credit_from_statement(predicate: str, value: dict, source_url: str) -> SourcedCredit | None:
    """Read one reviewed statement without guessing person identity across sources."""
    if predicate not in {"cast", "director", "writer"}:
        return None
    name = value.get("name")
    if not isinstance(name, str) or not name.strip() or not source_url.startswith("https://"):
        return None
    character = value.get("character")
    if not isinstance(character, str) or not character.strip():
        characters = value.get("characters")
        character = characters[0] if isinstance(characters, list) and characters and isinstance(characters[0], str) else None
    position = value.get("position")
    return SourcedCredit(
        name=name.strip(), role=predicate,
        character_name=character.strip() if isinstance(character, str) and character.strip() else None,
        position=position if isinstance(position, int) and position >= 0 else None,
        source_url=source_url,
    )


def character_qid(qualifiers: dict) -> str | None:
    """Only use an unambiguous explicit P453 entity qualifier."""
    if not isinstance(qualifiers, dict):
        return None
    values = set()
    snaks = qualifiers.get("P453", [])
    if not isinstance(snaks, list):
        return None
    for snak in snaks:
        data = snak.get("datavalue") if isinstance(snak, dict) else None
        value = data.get("value", {}) if isinstance(data, dict) else {}
        qid = value.get("id") if isinstance(value, dict) else None
        if isinstance(qid, str) and qid.startswith("Q") and qid[1:].isdigit():
            values.add(qid)
    return next(iter(values)) if len(values) == 1 else None


def credit_display_sort_key(item: SourcedCredit) -> tuple[int, int, int, str]:
    """Keep sourced actor-to-character credits visible within a capped list."""
    return (
        {"director": 0, "writer": 1, "cast": 2}[item.role],
        0 if item.role == "cast" and item.character_name else 1,
        item.position if item.position is not None else 10_000,
        item.name.casefold(),
    )


def _wikidata_labels(db: Session, qids: set[str]) -> dict[str, tuple[str, str, str | None]]:
    """Read labels only from the latest retained successful CC0 snapshot per QID."""
    if not qids:
        return {}
    rows = db.execute(select(SourceObject, SourceSnapshot).join(
        SourceSnapshot, SourceSnapshot.source_object_id == SourceObject.id,
    ).join(DataSource, DataSource.id == SourceObject.source_id).where(
        DataSource.name == "Wikidata", SourceObject.external_id.in_(qids),
        SourceSnapshot.fetch_status == "success", SourceSnapshot.license == "CC0 1.0",
    ).order_by(SourceObject.external_id, SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc())).all()
    latest = {}
    for obj, snap in rows:
        latest.setdefault(obj.external_id, snap)
    reverse = {snap.id: qid for qid, snap in latest.items()}
    candidates: dict[str, set[str]] = {}
    if reverse:
        statements = db.scalars(select(SourceAssertion).where(
            SourceAssertion.source_snapshot_id.in_(reverse), SourceAssertion.source_property == "wikidata:label:en",
            SourceAssertion.statement_locator == "labels.en",
        ))
        for statement in statements:
            qid = reverse[statement.source_snapshot_id]
            snap = latest[qid]
            value = statement.raw_value or {}
            label = value.get("text")
            url = snap.attribution_url or snap.canonical_url
            if ((statement.raw_subject or {}).get("wikidata_id") == qid and value.get("language") == "en"
                    and isinstance(label, str) and label.strip()
                    and label.strip() != qid and url.startswith("https://")):
                candidates.setdefault(qid, set()).add(label.strip())
    return {qid: (next(iter(names)), latest[qid].attribution_url or latest[qid].canonical_url,
                  latest[qid].source_revision)
            for qid, names in candidates.items() if len(names) == 1}


def sourced_credit_groups(db: Session, entity_id: UUID, *, limit_per_source: int = 20,
                          include_noncommercial: bool = False) -> tuple[SourcedCreditGroup, ...]:
    conditions = [
        Assertion.subject_entity_id == entity_id,
        Assertion.predicate.in_(("cast", "director", "writer")),
        Assertion.assertion_kind == "source_fact",
        Assertion.review_status.in_(("resolved", "published")),
    ]
    conditions.append(DataSource.rights_status.in_(
        displayable_rights_statuses(include_noncommercial=include_noncommercial),
    ))
    rows = db.execute(
        select(Assertion, DataSource).join(DataSource, DataSource.id == Assertion.source_id).where(*conditions)
    ).all()
    object_ids = {a.object_entity_id for a, source in rows if source.name == "Wikidata" and a.object_entity_id}
    people = {entity.id: entity for entity in db.scalars(select(CanonicalEntity).where(CanonicalEntity.id.in_(object_ids)))} if object_ids else {}
    qids = {person.wikidata_id for person in people.values() if person.wikidata_id}
    qids.update(qid for a, source in rows if source.name == "Wikidata" and (qid := character_qid(a.qualifiers or {})))
    labels = _wikidata_labels(db, qids)
    grouped: dict[UUID, tuple[DataSource, dict[tuple[str, str, str | None], SourcedCredit]]] = {}
    for assertion, source in rows:
        credit = credit_from_statement(assertion.predicate, assertion.value_json or {}, assertion.source_reference or source.url)
        if credit is None and source.name == "Wikidata" and assertion.object_entity_id in people:
            person = people[assertion.object_entity_id]
            actor_label = labels.get(person.wikidata_id or "") if person.entity_kind == "person" else None
            role_label = labels.get(character_qid(assertion.qualifiers or {}) or "") if assertion.predicate == "cast" else None
            source_url = assertion.source_reference or source.url
            if actor_label and source_url.startswith("https://"):
                credit = SourcedCredit(name=actor_label[0], role=assertion.predicate,
                    character_name=role_label[0] if role_label else None, position=None, source_url=source_url,
                    name_source_url=actor_label[1], name_source_revision=actor_label[2],
                    character_source_url=role_label[1] if role_label else None,
                    character_source_revision=role_label[2] if role_label else None)
        if credit is None:
            continue
        _, credits = grouped.setdefault(source.id, (source, {}))
        key = (credit.name.casefold(), credit.role, credit.character_name)
        credits.setdefault(key, credit)
    return tuple(
        SourcedCreditGroup(
            source_name=source.name, source_license=source.license, rights_status=source.rights_status,
            credits=tuple(sorted(credits.values(), key=credit_display_sort_key)[:limit_per_source]),
        )
        for source, credits in sorted(grouped.values(), key=lambda pair: (pair[0].rights_status != "local_noncommercial_only", pair[0].name))
    )
