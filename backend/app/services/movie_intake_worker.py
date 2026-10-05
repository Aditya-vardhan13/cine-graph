"""Serial, resumable local intake worker; never runs inside a web request."""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import CanonicalEntity, Film, MovieIntakeJob, NarrativePassage
from app.services.imdb_dataset import ImdbDataset
from app.services.indian_wikipedia_manifest import _entity_from_snapshot
from app.services.movie_data_gateway import MovieSeed, run_ingestion
from app.services.reconcile_manifest_identities import (
    imdb_film_for_identifier, prepare_qid_subject, reconcile_one,
)
from app.services.reconcile_manifest_languages import reconcile_one as reconcile_language
from app.services.review_wikidata_imdb_ids import review_one as review_imdb_ids
from app.services.source_assertion_projection import project_source_assertions
from app.services.tmdb_client import bearer_token
from app.services.wikidata_imdb_resolver import acquire, imdb_qid_query, qids_by_imdb
from app.services.wikidata_raw import ingest_selected_qids
from app.services.wikipedia_raw import ingest_title_year_entries
from app.services.wikipedia_research import extract_passages


def claim_next(db: Session) -> MovieIntakeJob | None:
    stale = datetime.now(timezone.utc) - timedelta(minutes=30)
    job = db.scalar(select(MovieIntakeJob).where(
        (MovieIntakeJob.status == "queued") |
        ((MovieIntakeJob.status == "running") & (MovieIntakeJob.updated_at < stale)),
    ).order_by(MovieIntakeJob.created_at).with_for_update(skip_locked=True).limit(1))
    if job is None:
        return None
    job.status = "running"
    job.stage = "imdb_tmdb"
    job.attempts += 1
    job.updated_at = datetime.now(timezone.utc)
    db.commit()
    return job


def progress(db: Session, job: MovieIntakeJob, stage: str) -> None:
    job.stage = stage
    job.updated_at = datetime.now(timezone.utc)
    db.commit()


def finish(db: Session, job: MovieIntakeJob, status: str, reason: str | None = None) -> None:
    job.status = status
    job.stage = status
    job.review_reason = reason
    job.updated_at = datetime.now(timezone.utc)
    db.commit()


def has_plot(db: Session, entity_id) -> bool:
    sections = db.scalars(select(NarrativePassage.section_locator).where(
        NarrativePassage.subject_entity_id == entity_id,
    ))
    return any(section.replace(" / ", "/").casefold().split("/", 1)[0]
               in {"plot", "plot-summary", "synopsis", "premise", "story", "storyline"}
               for section in sections)


def process_one(db: Session, job: MovieIntakeJob, *, dataset: ImdbDataset,
                tmdb_token: str | None, cache_dir: Path) -> None:
    progress(db, job, "wikidata_identity")
    qids = qids_by_imdb(acquire(imdb_qid_query([job.imdb_id]), cache_dir)).get(job.imdb_id, [])
    if len(qids) != 1:
        finish(db, job, "needs_review", f"Wikidata IMDb P345 resolved to {len(qids)} items; manual identity review required")
        return
    qid = qids[0]
    seed = MovieSeed(job.title, job.year, imdb_id=job.imdb_id, wikidata_id=qid,
                     selection_source_url=job.submitted_url or
                     f"https://www.imdb.com/title/{job.imdb_id}/")
    progress(db, job, "wikidata_snapshot")
    ingest_selected_qids(db, [qid], manifest_uri=f"movie_intake_job:{job.id}")
    prepare_qid_subject(db, seed, apply=True)
    db.commit()
    project_source_assertions(db, qids={qid})
    db.commit()
    review = review_imdb_ids(db, dataset, seed, apply=True)
    if review["status"] not in {"unambiguous", "quarantined"}:
        finish(db, job, "needs_review", review.get("reason", "Wikidata IMDb identifiers conflict"))
        return
    prior = imdb_film_for_identifier(db, job.imdb_id)
    if prior is not None:
        progress(db, job, "identity_reconciliation")
        try:
            reconcile_one(db, seed, apply=True)
        except ValueError as exc:
            db.rollback()
            finish(db, job, "needs_review", str(exc))
            return
    progress(db, job, "imdb_tmdb")
    report = run_ingestion(db, seeds=[seed], dataset=dataset,
                           manifest=f"movie_intake_job:{job.id}", create=True,
                           collection="operator-selected-films-v1", tmdb_token=tmdb_token,
                           collection_language_code="mul")
    row = report["results"][0]
    if row.get("error") or not row.get("film_id"):
        finish(db, job, "needs_review" if row.get("error") else "failed",
               row.get("error") or row.get("identity") or "IMDb ingestion failed")
        return
    film = db.get(Film, UUID(row["film_id"]))
    job.film_entity_id = film.entity_id
    db.commit()
    gaps = []
    if not isinstance(row.get("tmdb"), dict):
        gaps.append("TMDb exact IMDb cross-ID not verified")
    entity = db.scalar(select(CanonicalEntity).where(CanonicalEntity.wikidata_id == qid))
    job.film_entity_id = entity.id
    db.commit()
    language = reconcile_language(db, qid, apply=True)
    db.commit()
    if language["status"] == "review_required":
        gaps.append("original-language profile needs review")
    progress(db, job, "wikipedia_narrative")
    source = _entity_from_snapshot(db, qid)
    wiki_title = (source or {}).get("sitelinks", {}).get("enwiki", {}).get("title")
    if wiki_title:
        raw = ingest_title_year_entries(db, [{"title": job.title, "year": job.year,
                                               "wikidata_id": qid, "wikipedia_title": wiki_title,
                                               "verified_wikidata_sitelink": True}],
                                            manifest_uri=f"movie_intake_job:{job.id}")
        if raw["resolved"]:
            extract_passages(db, qid)
            db.commit()
        else:
            gaps.append("Wikipedia revision/QID verification failed")
    else:
        gaps.append("no verified English Wikipedia sitelink")
    if not has_plot(db, entity.id):
        gaps.append("no full plot passage")
    finish(db, job, "ready_with_gaps" if gaps else "ready", "; ".join(gaps) if gaps else None)


def run_once(*, tmdb_key_file: Path, cache_dir: Path) -> bool:
    settings = get_settings()
    dataset = ImdbDataset(Path(settings.imdb_data_dir), Path(settings.imdb_index_dir))
    tmdb_token = bearer_token(tmdb_key_file) if tmdb_key_file.is_file() else None
    with SessionLocal() as db:
        job = claim_next(db)
        if job is None:
            return False
        try:
            process_one(db, job, dataset=dataset, tmdb_token=tmdb_token, cache_dir=cache_dir)
        except Exception as exc:
            db.rollback()
            job = db.get(MovieIntakeJob, job.id)
            finish(db, job, "failed", f"{type(exc).__name__}: {exc}"[:1000])
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Process local movie intake jobs serially")
    parser.add_argument("--tmdb-key-file", type=Path, default=Path("/run/secrets/tmdb_api.env"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/wikidata-imdb-cache"))
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.poll_seconds <= 60:
        parser.error("--poll-seconds must be between 1 and 60")
    while True:
        found = run_once(tmdb_key_file=args.tmdb_key_file, cache_dir=args.cache_dir)
        if args.once:
            break
        if not found:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
