"""Revisioned Wikipedia filmography credits for explicit, reviewed film lists.

This is an operator-only supplement, not a general Wikipedia crawler. A row
only becomes an operational cast assertion when its film resolves independently
to the same IMDb-anchored catalog entity as an explicit manifest entry.
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    Assertion, AssertionEvidence, DataSource, EntityResolution, Film,
    RawIngestionRun, SourceAssertion, SourceObject,
)
from app.services.imdb_dataset import ImdbDataset, normalize_title
from app.services.movie_data_gateway import MovieSeed, manifest_seeds, resolve_seed
from app.services.raw_snapshots import snapshot, source_object
from app.services.wikipedia_raw import (
    page_lookup, request_interval_seconds, revision_payload,
    source_for_wikipedia, wikipedia_api_policy,
)


VERSION = "actor-filmography-table-v1"
YEAR = re.compile(r'(?m)^\|\s*(?:rowspan="\d+"\s*\|\s*)?(\d{4})\s*$')
TITLE = re.compile(r'(?m)^!\s*scope="row"\s*\|\s*\'\'\[\[([^\]]+)\]\]\'\'')


@dataclass(frozen=True)
class FilmographyRow:
    ordinal: int
    year: int
    title: str
    wikipedia_title: str
    character: str


def parse_filmography(wikitext: str) -> list[FilmographyRow]:
    """Read the first Filmography wikitable; fail closed on unknown layout."""
    section = re.search(r"(?m)^==\s*Filmography\s*==\s*$", wikitext)
    if not section:
        raise ValueError("Filmography section not found")
    table = re.search(r"\{\|[^\n]*wikitable[^\n]*\n(.*?)\n\|\}",
                      wikitext[section.end():], re.DOTALL)
    if not table:
        raise ValueError("Filmography table not found")
    rows: list[FilmographyRow] = []
    current_year: int | None = None
    for ordinal, fragment in enumerate(re.split(r"(?m)^\|-\s*$", table.group(1))[1:]):
        year = YEAR.search(fragment)
        if year:
            current_year = int(year.group(1))
        title = TITLE.search(fragment)
        if not title or current_year is None:
            continue
        target, separator, display = title.group(1).partition("|")
        lines_after_title = fragment[title.end():].splitlines()
        role = next((line[1:].strip() for line in lines_after_title
                     if line.startswith("|") and not line.startswith("| style=")), "")
        role = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", role)
        role = role.replace("''", "").strip()
        rows.append(FilmographyRow(ordinal, current_year,
                                  (display if separator else target).strip(),
                                  target.strip(), role))
    if not rows:
        raise ValueError("No filmography rows parsed")
    return rows


def _film_for_imdb(db: Session, imdb_id: str) -> Film | None:
    return db.scalar(select(Film).join(
        EntityResolution, EntityResolution.entity_id == Film.entity_id,
    ).join(SourceObject, SourceObject.id == EntityResolution.source_object_id
    ).join(DataSource, DataSource.id == SourceObject.source_id).where(
        DataSource.name == "IMDb Non-Commercial Datasets",
        SourceObject.external_id == imdb_id,
        EntityResolution.status == "resolved",
    ))


def match_row(row: FilmographyRow, seeds: list[MovieSeed]) -> MovieSeed | None:
    matches = [seed for seed in seeds if seed.year == row.year and
               normalize_title(seed.title) == normalize_title(row.title)]
    return matches[0] if len(matches) == 1 else None


def ingest_actor_filmography(db: Session, *, actor_page: str, actor_name: str,
                             actor_imdb_id: str, seeds: list[MovieSeed],
                             dataset: ImdbDataset) -> dict[str, Any]:
    import time

    source = source_for_wikipedia(db)
    policy = wikipedia_api_policy(db, source)
    if policy.decision != "allowed":
        raise ValueError("Wikipedia API access policy is not allowed")
    db.commit()
    lookup = page_lookup(actor_page)
    if not lookup:
        raise ValueError("Actor filmography page not found")
    time.sleep(request_interval_seconds())
    page = revision_payload(lookup["resolved_title"])
    if not page:
        raise ValueError("Actor filmography revision not found")
    revision = (page.get("revisions") or [{}])[0]
    revision_id = revision.get("revid")
    wikitext = revision.get("slots", {}).get("main", {}).get("content", "")
    rows = parse_filmography(wikitext)
    run = RawIngestionRun(
        source_id=source.id, access_policy_id=policy.id,
        adapter_name="wikipedia_actor_filmography", adapter_version=VERSION,
        manifest_uri=actor_page, status="running", records_requested=len(rows),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    url = lookup["fullurl"]
    item = source_object(db, source=source, external_id=f"enwiki:{page['pageid']}",
                         object_kind="wiki_page", canonical_url=url)
    payload = json.dumps(page, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    stored, created = snapshot(
        db, item=item, run=run, payload=payload,
        source_revision=str(revision_id) if revision_id else None,
        canonical_url=url, license=source.license, attribution_url=url,
        parser_version=VERSION,
    )
    projected = 0
    unmatched: list[dict[str, Any]] = []
    for row in rows:
        locator = f"filmography.table[0].row[{row.ordinal}]"
        raw = db.scalar(select(SourceAssertion).where(
            SourceAssertion.source_snapshot_id == stored.id,
            SourceAssertion.statement_locator == locator,
            SourceAssertion.extractor_version == VERSION,
        ))
        if raw is None:
            raw = SourceAssertion(
                source_snapshot_id=stored.id, statement_locator=locator,
                source_property="filmography", extractor_version=VERSION,
                raw_subject={"actor": actor_name, "actor_imdb_id": actor_imdb_id},
                raw_value={"film_title": row.title, "year": row.year,
                           "character": row.character, "wikipedia_title": row.wikipedia_title},
                raw_qualifiers={},
            )
            db.add(raw)
            db.flush()
        seed = match_row(row, seeds)
        if not seed:
            unmatched.append({"title": row.title, "year": row.year, "reason": "not_in_manifest"})
            continue
        imdb_id, identity = resolve_seed(dataset, seed)
        film = _film_for_imdb(db, imdb_id) if imdb_id else None
        if film is None:
            unmatched.append({"title": row.title, "year": row.year, "reason": identity})
            continue
        if db.scalar(select(AssertionEvidence.id).where(
            AssertionEvidence.source_assertion_id == raw.id,
        )):
            continue
        assertion = Assertion(
            subject_entity_id=film.entity_id, predicate="cast",
            source_property="filmography", assertion_kind="source_fact",
            value_json={"imdb_person_id": actor_imdb_id, "name": actor_name,
                        "characters": [row.character] if row.character else [],
                        "role": "filmography", "position": None},
            qualifiers={"filmography_year": row.year},
            source_id=source.id, source_reference=url,
            source_revision=str(revision_id) if revision_id else None,
            derivation_version=VERSION, review_status="resolved",
        )
        db.add(assertion)
        db.add(AssertionEvidence(
            assertion=assertion, source_assertion_id=raw.id,
            evidence_type="source_assertion", reference=f"{url}#Filmography",
            note="Matched filmography row to an independently IMDb-anchored manifest film.",
        ))
        projected += 1
    run.records_snapshotted = int(created)
    # Rows outside the explicit manifest are expected source context, not
    # failed fetches or permission to extend the corpus implicitly.
    run.records_failed = 0
    run.status = "complete"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"page": url, "revision": revision_id, "rows": len(rows),
            "projected": projected, "unmatched": unmatched}


def main() -> None:
    parser = argparse.ArgumentParser(description="Operator-only actor filmography supplement")
    parser.add_argument("--actor-page", required=True)
    parser.add_argument("--actor-name", required=True)
    parser.add_argument("--actor-imdb-id", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("/imports/imdb"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    with SessionLocal() as db:
        result = ingest_actor_filmography(
            db, actor_page=args.actor_page, actor_name=args.actor_name,
            actor_imdb_id=args.actor_imdb_id,
            seeds=manifest_seeds(args.manifest),
            dataset=ImdbDataset(args.data_dir, args.index_dir),
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"rows": result["rows"], "projected": result["projected"],
                      "unmatched": len(result["unmatched"]), "report": str(args.report)}))


if __name__ == "__main__":
    main()
