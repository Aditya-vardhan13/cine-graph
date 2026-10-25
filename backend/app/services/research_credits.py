"""Attributable credit read model; source statements stay source-specific."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assertion, DataSource


@dataclass(frozen=True)
class SourcedCredit:
    name: str
    role: str
    character_name: str | None
    position: int | None
    source_url: str


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


def sourced_credit_groups(db: Session, entity_id: UUID, *, limit_per_source: int = 20,
                          include_noncommercial: bool = False) -> tuple[SourcedCreditGroup, ...]:
    conditions = [
        Assertion.subject_entity_id == entity_id,
        Assertion.predicate.in_(("cast", "director", "writer")),
        Assertion.assertion_kind == "source_fact",
        Assertion.review_status.in_(("resolved", "published")),
    ]
    if not include_noncommercial:
        conditions.append(DataSource.rights_status != "local_noncommercial_only")
    rows = db.execute(
        select(Assertion, DataSource).join(DataSource, DataSource.id == Assertion.source_id).where(*conditions)
    ).all()
    grouped: dict[UUID, tuple[DataSource, dict[tuple[str, str, str | None], SourcedCredit]]] = {}
    for assertion, source in rows:
        credit = credit_from_statement(assertion.predicate, assertion.value_json or {}, assertion.source_reference or source.url)
        if credit is None:
            continue
        _, credits = grouped.setdefault(source.id, (source, {}))
        key = (credit.name.casefold(), credit.role, credit.character_name)
        credits.setdefault(key, credit)
    return tuple(
        SourcedCreditGroup(
            source_name=source.name, source_license=source.license, rights_status=source.rights_status,
            credits=tuple(sorted(credits.values(), key=lambda item: (
                {"director": 0, "writer": 1, "cast": 2}[item.role],
                item.position if item.position is not None else 10_000, item.name,
            ))[:limit_per_source]),
        )
        for source, credits in sorted(grouped.values(), key=lambda pair: (pair[0].rights_status != "local_noncommercial_only", pair[0].name))
    )
