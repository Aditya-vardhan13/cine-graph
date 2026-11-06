"""Serial, resumable local intake worker; never runs inside a web request."""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import CanonicalEntity, DataSource, Film, MovieIntakeJob, SourceObject, SourceSnapshot
from app.services.current_narrative_passages import current_passage_rows
from app.services.imdb_dataset import ImdbDataset
from app.services.indian_wikipedia_manifest import _entity_from_snapshot
from app.services.movie_intake_identity import identity_issue
from app.services.movie_data_gateway import MovieSeed, run_ingestion
from app.services.reconcile_manifest_identities import (
    imdb_film_for_identifier, prepare_qid_subject, reconcile_one,
)
from app.services.reconcile_manifest_languages import reconcile_one as reconcile_language
from app.services.review_wikidata_imdb_ids import review_one as review_imdb_ids
from app.services.credit_target_manifest import select_credit_target_qids
from app.services.source_assertion_projection import project_source_assertions
from app.services.tmdb_client import bearer_token
from app.services.wikidata_raw import entity_from_entitydata, ingest_selected_qids, ingest_selected_credit_labels
from app.services.wikipedia_article_capture import WikipediaArticleFetcher
from app.services.wikipedia_article_html import article_url, parse_article_html, validate_article_url
from app.services.wikipedia_raw import ingest_captured_article
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
    return any(passage.section_locator.replace(" / ", "/").casefold().split("/", 1)[0]
               in {"plot", "plot-summary", "synopsis", "premise", "story", "storyline"}
               for passage, _ in current_passage_rows(db, {entity_id}))


def retained_wikidata_entity(db: Session, qid: str) -> dict:
    """Read the exact retained EntityData bytes; never refetch or reserialize."""
    source = db.scalar(select(DataSource).where(DataSource.name == "Wikidata"))
    item = db.scalar(select(SourceObject).where(
        SourceObject.source_id == source.id if source else False,
        SourceObject.external_id == qid,
    ))
    snapshot = db.scalar(select(SourceSnapshot).where(
        SourceSnapshot.source_object_id == item.id if item else False,
        SourceSnapshot.fetch_status == "success",
    ).order_by(SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc()))
    if snapshot is None or not snapshot.storage_uri:
        raise ValueError(f"No exact retained EntityData bytes are available for {qid}.")
    storage_path = Path(unquote(urlsplit(snapshot.storage_uri).path))
    return entity_from_entitydata(json.loads(storage_path.read_bytes()), qid)


def process_one(db: Session, job: MovieIntakeJob, *, dataset: ImdbDataset,
                tmdb_token: str | None, cache_dir: Path) -> None:
    del cache_dir  # Legacy argument retained for CLI compatibility; no WDQS cache is read.
    if job.year is None:
        finish(db, job, "needs_review", "A release year is required for identity verification")
        return
    progress(db, job, "wikipedia_identity")
    settings = get_settings()
    requested_article_url = (
        validate_article_url(job.submitted_url)
        if job.submitted_url and job.submitted_url.startswith("https://en.wikipedia.org/")
        else article_url(job.title)
    )
    try:
        with WikipediaArticleFetcher(
            user_agent=settings.wikidata_user_agent,
            interval_seconds=max(1.0, settings.source_request_interval_seconds),
        ) as fetcher:
            article_payload, article_url_resolved, _, media_type = fetcher.fetch(requested_article_url)
            robots_sha256 = fetcher.robots_sha256 or ""
        article = parse_article_html(article_payload, canonical_url=article_url_resolved)
    except FileNotFoundError as exc:
        finish(db, job, "needs_review", f"No matching Wikipedia article page: {exc}")
        return
    qid = article.metadata.wikidata_id
    seed = MovieSeed(job.title, job.year, imdb_id=job.imdb_id, wikidata_id=qid,
                     selection_source_url=job.submitted_url or
                     f"https://www.imdb.com/title/{job.imdb_id}/")
    progress(db, job, "wikidata_snapshot")
    ingest_selected_qids(db, [qid], manifest_uri=f"movie_intake_job:{job.id}")
    try:
        entity_data = retained_wikidata_entity(db, qid)
        issue = identity_issue(article_qid=qid, entity=entity_data, title=job.title,
                               year=job.year, imdb_id=job.imdb_id)
        if issue:
            finish(db, job, "needs_review", issue)
            return
        prepare_qid_subject(db, seed, apply=True)
    except ValueError as exc:
        db.rollback()
        finish(db, job, "needs_review", str(exc))
        return
    db.commit()
    project_source_assertions(db, qids={qid})
    db.commit()
    progress(db, job, "wikidata_credit_labels")
    credit_targets = select_credit_target_qids(entity_data)
    if credit_targets:
        ingest_selected_credit_labels(
            db, credit_targets, manifest_uri=f"movie_intake_job:{job.id}:credit_labels",
        )
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
    if wiki_title and wiki_title == article.metadata.title:
        ingest_captured_article(
            db, payload=article_payload, canonical_url=article_url_resolved,
            media_type=media_type, expected_qid=qid, robots_sha256=robots_sha256,
            manifest_uri=f"movie_intake_job:{job.id}",
        )
        extract_passages(db, qid)
        db.commit()
    elif wiki_title:
        gaps.append("captured Wikipedia article title differs from the verified English sitelink")
    else:
        gaps.append("no verified English Wikipedia sitelink")
    if not has_plot(db, entity.id):
        gaps.append("no full plot passage")
    # This worker captures and extracts source evidence only. Rights review,
    # chunking and embedding are separate, explicit stages.
    finish(db, job, "captured_with_gaps" if gaps else "captured", "; ".join(gaps) if gaps else None)


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
