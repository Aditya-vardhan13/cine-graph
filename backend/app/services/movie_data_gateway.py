"""Replayable local movie enrichment from IMDb TSVs and the TMDb API.

This is an explicit operator job, never part of an API request or app startup.
Restricted-source assertions remain tagged non-commercial and source-linked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    Assertion, AssertionEvidence, CanonicalEntity, DataSource, EntityResolution,
    Film, LanguageEdition, NarrativePassage, RawIngestionRun, ReferenceCollection,
    ReferenceCollectionMembership, SourceAccessPolicy, SourceAssertion,
    SourceObject, SourceSnapshot,
)
from app.services.imdb_dataset import IMDB_ID, ImdbDataset, normalize_title
from app.services.movie_source_facts import MovieSourceFact, imdb_facts, tmdb_facts
from app.services.raw_snapshots import snapshot, source_object
from app.services.research_metadata import LANGUAGE_CODES
from app.services.tmdb_client import CLIENT_VERSION, TmdbAccessError, TmdbClient, bearer_token


IMDB_SOURCE = "IMDb Non-Commercial Datasets"
TMDB_SOURCE = "TMDb Developer API"
IMDB_VERSION = "imdb-tsv-local-v1"
PROJECTOR_VERSION = "movie-source-facts-v2"
LANGUAGE_NAMES = {
    "en": ("English", "Latin"), "te": ("Telugu", "Telugu"),
    "hi": ("Hindi", "Devanagari"), "ta": ("Tamil", "Tamil"),
    "ml": ("Malayalam", "Malayalam"), "kn": ("Kannada", "Kannada"),
    "bn": ("Bengali", "Bengali"), "mr": ("Marathi", "Devanagari"),
    "ur": ("Urdu", "Arabic"), "pa": ("Punjabi", "Gurmukhi"),
    "und": ("Undetermined", "Unknown"), "mul": ("Multiple", "Unknown"),
}


@dataclass(frozen=True)
class MovieSeed:
    title: str
    year: int | None = None
    imdb_id: str | None = None
    language_code: str | None = None
    film_id: UUID | None = None
    entity_id: UUID | None = None
    imdb_person_id: str | None = None
    selection_source_url: str | None = None
    replaces_imdb_id: str | None = None
    wikidata_id: str | None = None
    selection_signals: dict[str, Any] | None = None


def source_registration(db: Session, name: str) -> tuple[DataSource, SourceAccessPolicy]:
    definitions = {
        IMDB_SOURCE: {
            "url": "https://developer.imdb.com/non-commercial-datasets/",
            "mode": "dump", "license": "IMDb Non-Commercial Datasets terms",
            "policy_url": "https://developer.imdb.com/non-commercial-datasets/",
            "allowed_paths": ["operator-supplied-local-tsv"],
            "note": "Local research only; never deploy these snapshots or assertions in a commercial product without a separate licence.",
        },
        TMDB_SOURCE: {
            "url": "https://developer.themoviedb.org/docs/getting-started",
            "mode": "api", "license": "TMDb developer API non-commercial terms",
            "policy_url": "https://developer.themoviedb.org/docs/faq",
            "allowed_paths": ["/3/find/{id}", "/3/movie/{id}"],
            "note": "Developer key is for local non-commercial research; commercial publication needs TMDb licensing.",
        },
    }
    spec = definitions[name]
    source = db.scalar(select(DataSource).where(DataSource.name == name))
    if source is None:
        source = DataSource(
            name=name, url=spec["url"], source_type="film_metadata",
            license=spec["license"], rights_status="local_noncommercial_only",
            notes=spec["note"],
        )
        db.add(source)
        db.flush()
    elif source.rights_status != "local_noncommercial_only":
        raise ValueError(f"{name} has an unexpected rights status; review it before acquisition")
    policy = db.scalar(select(SourceAccessPolicy).where(
        SourceAccessPolicy.source_id == source.id,
        SourceAccessPolicy.access_mode == spec["mode"],
    ))
    if policy is None:
        policy = SourceAccessPolicy(
            source_id=source.id, access_mode=spec["mode"], policy_url=spec["policy_url"],
            allowed_paths=spec["allowed_paths"], required_user_agent=spec["mode"] == "api",
            max_requests_per_minute=100 if spec["mode"] == "api" else None,
            max_concurrency=1, decision="allowed", decision_notes=spec["note"],
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(policy)
        db.flush()
    if policy.decision != "allowed":
        raise ValueError(f"{name} access policy is not allowed")
    return source, policy


def start_run(db: Session, source: DataSource, policy: SourceAccessPolicy, *,
              adapter: str, requested: int, manifest: str | None) -> RawIngestionRun:
    run = RawIngestionRun(
        source_id=source.id, access_policy_id=policy.id, adapter_name=adapter,
        adapter_version=IMDB_VERSION if source.name == IMDB_SOURCE else CLIENT_VERSION,
        manifest_uri=manifest, status="running", records_requested=requested,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    return run


def existing_seeds(db: Session) -> tuple[list[MovieSeed], list[dict[str, str]]]:
    identifiers: dict[UUID, str] = {}
    for entity_id, value in db.execute(select(Assertion.subject_entity_id, Assertion.value_json).where(
        Assertion.predicate == "imdb_identifier",
        Assertion.review_status.in_(("resolved", "published")),
    )):
        tconst = (value or {}).get("value")
        if isinstance(tconst, str) and IMDB_ID.fullmatch(tconst):
            identifiers[entity_id] = tconst
    films = {film.entity_id: film for film in db.scalars(select(Film)) if film.entity_id}
    found, missing = [], []
    for entity in db.scalars(select(CanonicalEntity).where(
        CanonicalEntity.entity_kind == "film",
    ).order_by(CanonicalEntity.canonical_label)):
        tconst = identifiers.get(entity.id)
        film = films.get(entity.id)
        if tconst:
            language = film.original_language_code if film else _asserted_language(db, entity.id)
            found.append(MovieSeed(
                title=film.canonical_title if film else entity.canonical_label,
                # Legacy profile years are known to be wrong for some titles.
                # The reviewed external identifier, not that year, anchors identity.
                year=None, imdb_id=tconst, language_code=language,
                film_id=film.id if film else None, entity_id=entity.id,
            ))
        elif film:
            missing.append({"film_id": str(film.id), "title": film.canonical_title,
                            "wikidata_id": film.wikidata_id or ""})
    return found, missing


def _asserted_language(db: Session, entity_id: UUID) -> str | None:
    values = list(db.scalars(select(Assertion.value_json).where(
        Assertion.subject_entity_id == entity_id,
        Assertion.predicate == "original_language",
        Assertion.review_status.in_(("resolved", "published")),
    )))
    codes = {LANGUAGE_CODES.get((value or {}).get("wikidata_id")) for value in values}
    codes.discard(None)
    return next(iter(codes)) if len(codes) == 1 else None


def cached_tmdb_id(db: Session, film: Film, tconst: str) -> str | None:
    """Resume only a TMDb snapshot whose own IMDb cross-ID was projected."""
    candidates = db.execute(select(SourceObject.external_id, SourceSnapshot.id).join(
        DataSource, DataSource.id == SourceObject.source_id,
    ).join(
        EntityResolution, EntityResolution.source_object_id == SourceObject.id,
    ).join(
        SourceSnapshot, SourceSnapshot.id == EntityResolution.source_snapshot_id,
    ).where(
        DataSource.name == TMDB_SOURCE,
        EntityResolution.entity_id == film.entity_id,
        EntityResolution.status == "resolved",
        SourceSnapshot.fetch_status == "success",
    )).all()
    for tmdb_id, snapshot_id in candidates:
        identifiers = db.scalars(select(Assertion.value_json).join(
            AssertionEvidence, AssertionEvidence.assertion_id == Assertion.id,
        ).join(
            SourceAssertion, SourceAssertion.id == AssertionEvidence.source_assertion_id,
        ).where(
            Assertion.subject_entity_id == film.entity_id,
            Assertion.predicate == "imdb_identifier",
            Assertion.review_status.in_(("resolved", "published")),
            SourceAssertion.source_snapshot_id == snapshot_id,
            SourceAssertion.statement_locator == "external_ids.imdb_id",
        ))
        if any((value or {}).get("value") == tconst for value in identifiers):
            return tmdb_id
    return None


def manifest_seeds(path: Path) -> list[MovieSeed]:
    items: list[MovieSeed] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        title = str(value.get("title", "")).strip()
        year = value.get("year")
        if not title or (year is not None and (not isinstance(year, int) or not 1880 <= year <= 2100)):
            raise ValueError(f"Invalid film title/year on manifest line {line_number}")
        tconst = value.get("imdb_id")
        if tconst is not None and not IMDB_ID.fullmatch(str(tconst)):
            raise ValueError(f"Invalid IMDb ID on manifest line {line_number}")
        person_id = value.get("imdb_person_id")
        if person_id is not None and (not str(person_id).startswith("nm") or not str(person_id)[2:].isdigit()):
            raise ValueError(f"Invalid IMDb person ID on manifest line {line_number}")
        replaced = value.get("replaces_imdb_id")
        if replaced is not None and not IMDB_ID.fullmatch(str(replaced)):
            raise ValueError(f"Invalid replaced IMDb ID on manifest line {line_number}")
        entity_id = value.get("entity_id")
        wikidata_id = value.get("wikidata_id")
        if wikidata_id is not None and (not isinstance(wikidata_id, str)
                                        or not wikidata_id.startswith("Q")
                                        or not wikidata_id[1:].isdigit()):
            raise ValueError(f"Invalid Wikidata ID on manifest line {line_number}")
        if replaced and (not tconst or not entity_id or not value.get("selection_source_url")):
            raise ValueError(f"A correction needs new ID, entity ID and source URL on line {line_number}")
        signals = value.get("selection_signals")
        if signals is not None and not isinstance(signals, dict):
            raise ValueError(f"Selection signals must be an object on line {line_number}")
        items.append(MovieSeed(title=title, year=year, imdb_id=tconst,
                               language_code=value.get("language_code"),
                               imdb_person_id=person_id,
                               entity_id=UUID(str(entity_id)) if entity_id else None,
                               selection_source_url=value.get("selection_source_url"),
                               replaces_imdb_id=replaced, wikidata_id=wikidata_id,
                               selection_signals=signals))
    return items


def resolve_seed(dataset: ImdbDataset, seed: MovieSeed) -> tuple[str | None, str]:
    if seed.imdb_id:
        try:
            basics = dataset.rows("basics", seed.imdb_id)
        except ValueError:
            return None, "imdb_id_not_a_movie"
        if len(basics) != 1 or basics[0].get("titleType") not in {"movie", "tvMovie"}:
            return None, "imdb_id_not_a_movie"
        source_year = basics[0].get("startYear", "")
        if seed.year and source_year.isdigit() and abs(seed.year - int(source_year)) > 1:
            return None, "explicit_id_year_conflict"
        return seed.imdb_id, "explicit_imdb_id"
    matches = [row for row in dataset.search_title(seed.title, seed.year)
               if seed.year is None or row["year"] == seed.year]
    query = normalize_title(seed.title)
    exact_ids = {row["tconst"] for row in matches
                 if normalize_title(row["title"]) == query}
    if len(exact_ids) == 1:
        return next(iter(exact_ids)), "unique_exact_title_year"

    # A near-title is a lead, never an identity proof by itself. Require a
    # second independent anchor: the supplied actor's IMDb principal credit.
    if seed.imdb_person_id:
        candidate_ids = exact_ids or {row["tconst"] for row in matches
                                      if row["score"] >= 0.90}
        credited = {tconst for tconst in candidate_ids if any(
            row.get("nconst") == seed.imdb_person_id
            for row in dataset.rows("principals", tconst)
        )}
        if len(credited) == 1:
            return next(iter(credited)), "title_year_actor_credit"
    return None, "ambiguous_or_unverified_title" if matches else "title_not_found"


def _language(db: Session, code: str | None) -> str:
    clean = (code or "und").strip().lower()
    if clean not in LANGUAGE_NAMES:
        clean = "und"
    if db.get(LanguageEdition, clean) is None:
        display, script = LANGUAGE_NAMES[clean]
        db.add(LanguageEdition(code=clean, display_name=display, native_name=display,
                               script=script, enabled=False, status="planned"))
        db.flush()
    return clean


def film_for_seed(db: Session, dataset: ImdbDataset, seed: MovieSeed, tconst: str,
                  *, create: bool) -> Film:
    if seed.film_id:
        film = db.get(Film, seed.film_id)
        if film is None or film.entity_id is None:
            raise ValueError("Existing film has no canonical entity")
        return film
    already = db.scalar(select(Film).join(EntityResolution,
        EntityResolution.entity_id == Film.entity_id).join(SourceObject,
        SourceObject.id == EntityResolution.source_object_id).join(DataSource,
        DataSource.id == SourceObject.source_id).where(
            DataSource.name == IMDB_SOURCE, SourceObject.external_id == tconst,
            EntityResolution.status == "resolved",
    ))
    if already:
        if seed.wikidata_id:
            existing_entity = db.get(CanonicalEntity, already.entity_id)
            if existing_entity.wikidata_id != seed.wikidata_id:
                raise ValueError("IMDb film and manifest Wikidata identity need explicit reconciliation")
        return already
    if not create and seed.entity_id is None:
        raise ValueError("Movie is not in the catalog; use --create for an explicit addition")
    basic = dataset.rows("basics", tconst)[0]
    if seed.year and basic.get("startYear", "").isdigit() and abs(seed.year - int(basic["startYear"])) > 1:
        raise ValueError("Manifest year conflicts with IMDb title")
    # Never use a year-only value as an invented January 1 release date.
    entity = db.get(CanonicalEntity, seed.entity_id) if seed.entity_id else None
    if seed.wikidata_id:
        qid_entity = db.scalar(select(CanonicalEntity).where(
            CanonicalEntity.wikidata_id == seed.wikidata_id,
        ))
        if entity and qid_entity and entity.id != qid_entity.id:
            raise ValueError("Manifest entity and Wikidata identifier identify different films")
        entity = entity or qid_entity
    if entity is None:
        entity = CanonicalEntity(entity_kind="film", canonical_label=basic["primaryTitle"],
                                 wikidata_id=seed.wikidata_id)
        db.add(entity)
        db.flush()
    elif entity.entity_kind == "unknown_work" and seed.wikidata_id:
        # Existing unresolved lineage targets may later be identified as films.
        # Promote only after the retained Wikidata source statements themselves
        # have been projected into reviewed, evidence-linked assertions.
        wikidata = db.scalar(select(DataSource).where(DataSource.name == "Wikidata"))
        source_values = list(db.scalars(select(Assertion).where(
            Assertion.subject_entity_id == entity.id,
            Assertion.source_id == wikidata.id if wikidata else False,
            Assertion.review_status.in_(("resolved", "published")),
            Assertion.predicate.in_(("instance_of", "imdb_identifier")),
        )))
        is_film = any(row.predicate == "instance_of" and
                      (row.value_json or {}).get("wikidata_id") == "Q11424"
                      for row in source_values)
        id_matches = any(row.predicate == "imdb_identifier" and
                         (row.value_json or {}).get("value") == tconst
                         for row in source_values)
        if not (is_film and id_matches):
            raise ValueError("Unclassified work lacks reviewed film and IMDb-ID source evidence")
        entity.entity_kind = "film"
    elif entity.entity_kind != "film":
        raise ValueError("Manifest Wikidata identifier is attached to a non-film entity")
    current_film = db.scalar(select(Film).where(Film.entity_id == entity.id))
    if current_film:
        identifiers = [(value or {}).get("value") for value in db.scalars(
            select(Assertion.value_json).where(
                Assertion.subject_entity_id == entity.id,
                Assertion.predicate == "imdb_identifier",
                Assertion.review_status.in_(("resolved", "published")),
            )
        )]
        if identifiers and any(value != tconst for value in identifiers):
            raise ValueError("Existing film has a conflicting active IMDb identifier")
        return current_film
    film = Film(
        entity_id=entity.id, canonical_title=basic["primaryTitle"],
        original_language_code=_language(db, seed.language_code),
        country_codes=[], wikidata_id=entity.wikidata_id,
        review_status="published" if seed.entity_id and entity.wikidata_id else "review_required",
    )
    db.add(film)
    db.flush()
    return film


def _retract_superseded(db: Session, item: SourceObject, current: SourceSnapshot) -> int:
    old = list(db.scalars(select(Assertion).join(
        AssertionEvidence, AssertionEvidence.assertion_id == Assertion.id,
    ).join(SourceAssertion, SourceAssertion.id == AssertionEvidence.source_assertion_id
    ).join(SourceSnapshot, SourceSnapshot.id == SourceAssertion.source_snapshot_id
    ).where(SourceSnapshot.source_object_id == item.id,
            or_(SourceSnapshot.id != current.id,
                Assertion.derivation_version != PROJECTOR_VERSION),
            Assertion.derivation_version.like("movie-source-facts-%"),
            Assertion.review_status != "retracted")).unique())
    for assertion in old:
        assertion.review_status = "retracted"
    return len(old)


def persist_movie_bundle(db: Session, *, run: RawIngestionRun, source: DataSource,
                         external_id: str, film: Film, bundle: dict[str, Any],
                         facts: list[MovieSourceFact], canonical_url: str,
                         revision: str | None,
                         snapshot_root: Path | None = None) -> dict[str, int]:
    item = source_object(db, source=source, external_id=external_id,
                         object_kind="film", canonical_url=canonical_url)
    payload = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    stored, created = snapshot(
        db, item=item, run=run, payload=payload, source_revision=revision,
        canonical_url=canonical_url, license=source.license, attribution_url=canonical_url,
        parser_version=IMDB_VERSION if source.name == IMDB_SOURCE else CLIENT_VERSION,
        storage_root=snapshot_root,
    )
    method = "imdb_id_exact" if source.name == IMDB_SOURCE else "tmdb_imdb_cross_id_exact"
    resolution = db.scalar(select(EntityResolution).where(
        EntityResolution.source_object_id == item.id,
        EntityResolution.entity_id == film.entity_id,
        EntityResolution.source_snapshot_id == stored.id,
    ))
    if resolution is None:
        db.add(EntityResolution(
            source_object_id=item.id, source_snapshot_id=stored.id,
            entity_id=film.entity_id, method=method, confidence=1.0,
            status="resolved", rationale="Exact external film identifier, not a title-only match.",
        ))
    retracted = _retract_superseded(db, item, stored)
    existing = {row.statement_locator: row for row in db.scalars(select(SourceAssertion).where(
        SourceAssertion.source_snapshot_id == stored.id,
        SourceAssertion.extractor_version == PROJECTOR_VERSION,
    ))}
    raw_created = 0
    for fact in facts:
        if fact.locator not in existing:
            raw = SourceAssertion(
                source_snapshot_id=stored.id, statement_locator=fact.locator,
                source_property=fact.source_property,
                raw_subject={"external_id": external_id, "title": film.canonical_title},
                raw_value=fact.value, raw_qualifiers=fact.qualifiers,
                extractor_version=PROJECTOR_VERSION,
            )
            db.add(raw)
            existing[fact.locator] = raw
            raw_created += 1
    db.flush()
    raw_ids = [raw.id for raw in existing.values()]
    linked = set(db.scalars(select(AssertionEvidence.source_assertion_id).where(
        AssertionEvidence.source_assertion_id.in_(raw_ids),
    ))) if raw_ids else set()
    projected = 0
    for fact in facts:
        raw = existing[fact.locator]
        if raw.id in linked:
            continue
        assertion = Assertion(
            subject_entity_id=film.entity_id, predicate=fact.predicate,
            source_property=fact.source_property, value_json=fact.value,
            qualifiers=fact.qualifiers, assertion_kind="source_fact", source_id=source.id,
            source_reference=canonical_url, source_revision=revision,
            derivation_version=PROJECTOR_VERSION, review_status=fact.review_status,
        )
        db.add(assertion)
        db.add(AssertionEvidence(
            assertion=assertion, source_assertion_id=raw.id,
            evidence_type="source_assertion", reference=f"{canonical_url}#{fact.locator}",
            note=f"Non-commercial local source; {PROJECTOR_VERSION}",
        ))
        projected += 1
    if source.name == TMDB_SOURCE:
        overview = bundle.get("overview", "")
        if isinstance(overview, str) and overview.strip():
            content = overview.strip()
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            present = db.scalar(select(NarrativePassage.id).where(
                NarrativePassage.source_snapshot_id == stored.id,
                NarrativePassage.section_locator == "tmdb.overview",
                NarrativePassage.ordinal == 0,
                NarrativePassage.content_hash == digest,
            ))
            if not present:
                db.add(NarrativePassage(
                    subject_entity_id=film.entity_id, source_snapshot_id=stored.id,
                    section_locator="tmdb.overview", section_title="TMDb overview",
                    ordinal=0, language_code="en", content=content, content_hash=digest,
                    citation_markers=[], extraction_version=CLIENT_VERSION,
                ))
    db.flush()
    return {"snapshot_created": int(created), "source_assertions": raw_created,
            "assertions_projected": projected,
            "assertions_retracted": retracted}


def add_to_collection(db: Session, film: Film, code: str, source_reference: str,
                      selection_signals: dict[str, Any] | None = None,
                      *, language_code: str = "en") -> None:
    collection = db.get(ReferenceCollection, code)
    if collection is None:
        _language(db, language_code)
        collection = ReferenceCollection(
            code=code, title=code.replace("_", " ").replace("-", " ").strip().title(),
            description="Operator-selected feature films with attributable source records; language is film-specific.",
            language_code=language_code, selection_method="operator_manifest", selection_version="v1",
            status="active",
        )
        db.add(collection)
        db.flush()
    present = db.scalar(select(ReferenceCollectionMembership.id).where(
        ReferenceCollectionMembership.collection_code == code,
        ReferenceCollectionMembership.entity_id == film.entity_id,
    ))
    if not present:
        db.add(ReferenceCollectionMembership(
            collection_code=code, entity_id=film.entity_id,
            selection_signals={"source": "operator_manifest", **(selection_signals or {})},
            source_reference=source_reference, status="included",
        ))


def retract_replaced_identifier(db: Session, dataset: ImdbDataset, seed: MovieSeed,
                                film: Film, new_id: str) -> int:
    """Retire only an explicit, independently invalidated prior identifier."""
    old_id = seed.replaces_imdb_id
    if not old_id:
        return 0
    if not seed.entity_id or seed.entity_id != film.entity_id or old_id == new_id:
        raise ValueError("Identifier correction is not anchored to the selected entity")
    if dataset.rows("basics", old_id):
        raise ValueError("Prior IMDb ID exists in the local dataset; manual review required")
    old = list(db.scalars(select(Assertion).where(
        Assertion.subject_entity_id == film.entity_id,
        Assertion.predicate == "imdb_identifier",
        Assertion.review_status.in_(("resolved", "published")),
    )))
    matching = [row for row in old if (row.value_json or {}).get("value") == old_id]
    if not matching:
        retracted = db.scalars(select(Assertion.value_json).where(
            Assertion.subject_entity_id == film.entity_id,
            Assertion.predicate == "imdb_identifier",
            Assertion.review_status == "retracted",
        ))
        if any((value or {}).get("value") == old_id for value in retracted):
            return 0
        raise ValueError("Expected prior IMDb identifier assertion was not found")
    for row in matching:
        row.review_status = "retracted"
    return len(matching)


def run_ingestion(db: Session, *, seeds: list[MovieSeed], dataset: ImdbDataset,
                  manifest: str | None, create: bool, collection: str | None,
                  tmdb_token: str | None = None, refresh_tmdb: bool = False,
                  collection_language_code: str = "en") -> dict[str, Any]:
    imdb_source, imdb_policy = source_registration(db, IMDB_SOURCE)
    tmdb_source, tmdb_policy = source_registration(db, TMDB_SOURCE) if tmdb_token else (None, None)
    db.commit()
    imdb_run = start_run(db, imdb_source, imdb_policy, adapter="imdb_local_tsv", requested=len(seeds), manifest=manifest)
    tmdb_run = (start_run(db, tmdb_source, tmdb_policy, adapter="tmdb_movie_details",
                          requested=len(seeds), manifest=manifest) if tmdb_source and tmdb_policy else None)
    results: list[dict[str, Any]] = []
    client = TmdbClient(tmdb_token) if tmdb_token else None
    try:
        for seed in seeds:
            result: dict[str, Any] = {"title": seed.title, "imdb_id": seed.imdb_id}
            try:
                tconst, identity = resolve_seed(dataset, seed)
                result["identity"] = identity
                if tconst is None:
                    imdb_run.records_failed += 1
                    db.commit()
                    results.append(result)
                    continue
                bundle = dataset.film_bundle(tconst)
                film = film_for_seed(db, dataset, seed, tconst, create=create)
                result["film_id"] = str(film.id)
                result["imdb_id"] = tconst
                result["imdb"] = persist_movie_bundle(
                    db, run=imdb_run, source=imdb_source, external_id=tconst,
                    film=film, bundle=bundle, facts=imdb_facts(bundle),
                    canonical_url=f"https://www.imdb.com/title/{tconst}/",
                    revision=bundle["dataset_sha256"]["basics"][:32],
                )
                result["retracted_identifiers"] = retract_replaced_identifier(
                    db, dataset, seed, film, tconst,
                )
                if collection:
                    add_to_collection(db, film, collection,
                                      seed.selection_source_url or manifest or f"https://www.imdb.com/title/{tconst}/",
                                      seed.selection_signals, language_code=collection_language_code)
                imdb_run.records_snapshotted += result["imdb"]["snapshot_created"]
                db.commit()
                if client and tmdb_run and tmdb_source:
                    cached = None if refresh_tmdb else cached_tmdb_id(db, film, tconst)
                    if cached:
                        result["tmdb"] = {"cached": True, "tmdb_id": cached}
                    else:
                        matches = client.find_imdb(tconst)
                        if len(matches) != 1:
                            result["tmdb"] = "missing_or_ambiguous_external_id"
                        else:
                            tmdb_id = matches[0].get("id")
                            tmdb_bundle = client.movie_bundle(tmdb_id)
                            if tmdb_bundle.get("external_ids", {}).get("imdb_id") != tconst:
                                result["tmdb"] = "external_id_conflict"
                            else:
                                result["tmdb"] = persist_movie_bundle(
                                    db, run=tmdb_run, source=tmdb_source, external_id=str(tmdb_id),
                                    film=film, bundle=tmdb_bundle, facts=tmdb_facts(tmdb_bundle),
                                    canonical_url=f"https://www.themoviedb.org/movie/{tmdb_id}",
                                    revision=None,
                                )
                                tmdb_run.records_snapshotted += result["tmdb"]["snapshot_created"]
                                db.commit()
            except TmdbAccessError as exc:
                db.rollback()
                result["tmdb"] = f"access_error:{exc}"
                # Stop further TMDb calls after denial or transport failure.
                client.close()
                client = None
                if tmdb_run:
                    tmdb_run = db.get(RawIngestionRun, tmdb_run.id)
                    tmdb_run.error_summary = str(exc)
                    tmdb_run.status = "failed"
                    db.commit()
            except Exception as exc:
                db.rollback()
                result.pop("film_id", None)
                result["error"] = f"{type(exc).__name__}: {exc}"
                imdb_run = db.get(RawIngestionRun, imdb_run.id)
                imdb_run.records_failed += 1
                db.commit()
            results.append(result)
    finally:
        if client:
            client.close()
    imdb_run = db.get(RawIngestionRun, imdb_run.id)
    imdb_run.status = "complete" if not imdb_run.records_failed else "failed"
    imdb_run.completed_at = datetime.now(timezone.utc)
    if tmdb_run:
        tmdb_run = db.get(RawIngestionRun, tmdb_run.id)
        if tmdb_run.status == "running":
            tmdb_run.status = "complete"
        tmdb_run.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"requested": len(seeds), "imdb_run_id": str(imdb_run.id),
            "tmdb_run_id": str(tmdb_run.id) if tmdb_run else None,
            "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Local non-commercial movie data gateway")
    parser.add_argument("--data-dir", type=Path, default=Path("/imports/imdb"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--existing", action="store_true")
    source.add_argument("--manifest", type=Path)
    parser.add_argument("--create", action="store_true", help="Create films for explicit manifest entries")
    parser.add_argument("--collection", default=None)
    parser.add_argument("--tmdb-key-file", type=Path)
    parser.add_argument("--refresh-tmdb", action="store_true",
                        help="Request TMDb again even when a verified local snapshot exists")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    with SessionLocal() as db:
        if args.existing:
            seeds, missing = existing_seeds(db)
        else:
            seeds, missing = manifest_seeds(args.manifest), []
        if args.limit:
            seeds = seeds[:args.limit]
        report = run_ingestion(
            db, seeds=seeds, dataset=ImdbDataset(args.data_dir, args.index_dir),
            manifest=str(args.manifest) if args.manifest else "existing_catalog",
            create=args.create, collection=args.collection,
            tmdb_token=bearer_token(args.tmdb_key_file) if args.tmdb_key_file else None,
            refresh_tmdb=args.refresh_tmdb,
        )
        report["existing_without_imdb_id"] = missing
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "requested": report["requested"],
        "with_imdb": sum(isinstance(row.get("imdb"), dict) for row in report["results"]),
        "with_tmdb": sum(isinstance(row.get("tmdb"), dict) for row in report["results"]),
        "errors": sum(bool(row.get("error")) for row in report["results"]),
        "unresolved_existing": len(missing),
        "report": str(args.report),
    }))


if __name__ == "__main__":
    main()
