"""Local operator intake API. No source fetching happens in HTTP handlers."""
from __future__ import annotations

import hmac
import re
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import MovieIntakeJob
from app.services.imdb_dataset import IMDB_ID, ImdbDataset


router = APIRouter(prefix="/api/v1/admin/intake", tags=["local-admin-intake"])
IMDB_URL_PATH = re.compile(r"/title/(tt\d{7,10})/?\Z")


def imdb_id_from_input(value: str) -> str | None:
    """Accept only explicit IMDb title IDs/URLs; never fetch arbitrary URLs."""
    text = value.strip()
    if IMDB_ID.fullmatch(text):
        return text
    parsed = urlparse(text)
    if parsed.scheme != "https" or parsed.hostname not in {"imdb.com", "www.imdb.com", "m.imdb.com"}:
        return None
    match = IMDB_URL_PATH.fullmatch(parsed.path)
    return match.group(1) if match else None


def require_operator(authorization: str | None = Header(default=None)) -> None:
    secret = get_settings().admin_intake_token
    if not secret or len(secret) < 24:
        raise HTTPException(status_code=503, detail="Local admin intake is not configured")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not authorization or not authorization.startswith("Bearer ") or not hmac.compare_digest(supplied, secret):
        raise HTTPException(status_code=401, detail="Operator key required")


def dataset() -> ImdbDataset:
    settings = get_settings()
    return ImdbDataset(Path(settings.imdb_data_dir), Path(settings.imdb_index_dir))


def job_out(job: MovieIntakeJob) -> dict:
    return {"id": str(job.id), "imdb_id": job.imdb_id, "title": job.title,
            "year": job.year, "status": job.status, "stage": job.stage,
            "attempts": job.attempts, "review_reason": job.review_reason,
            "film_entity_id": str(job.film_entity_id) if job.film_entity_id else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None}


class IntakeSelection(BaseModel):
    films: list[str] = Field(min_length=1, max_length=20)


def enqueue_films(db: Session, lookup: ImdbDataset, values: list[str]) -> list[MovieIntakeJob]:
    """Resolve every selection from the local dump before atomically queuing any."""
    chosen: dict[str, str | None] = {}
    for raw in values:
        imdb_id = imdb_id_from_input(raw)
        if imdb_id is None:
            raise ValueError(f"Use an IMDb title ID or HTTPS IMDb title URL: {raw[:100]}")
        chosen[imdb_id] = f"https://www.imdb.com/title/{imdb_id}/"
    rows = []
    for imdb_id, url in chosen.items():
        basics = lookup.rows("basics", imdb_id)
        if len(basics) != 1 or basics[0].get("titleType") not in {"movie", "tvMovie"}:
            raise ValueError(f"{imdb_id} is not a local IMDb movie")
        row = basics[0]
        year = row.get("startYear", "")
        rows.append((imdb_id, row["primaryTitle"], int(year) if year.isdigit() else None, url))
    for imdb_id, title, year, url in rows:
        db.execute(insert(MovieIntakeJob).values(imdb_id=imdb_id, title=title, year=year,
                                             submitted_url=url, status="queued", stage="queued",
                                             attempts=0).on_conflict_do_nothing(index_elements=["imdb_id"]))
    db.commit()
    return list(db.scalars(select(MovieIntakeJob).where(MovieIntakeJob.imdb_id.in_(chosen))))


@router.get("/suggest", dependencies=[Depends(require_operator)])
def suggest(q: str = Query(min_length=2, max_length=120)) -> dict:
    try:
        rows = dataset().suggest_titles(q)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Local IMDb index is unavailable or stale") from exc
    return {"results": [{"imdb_id": row["tconst"], "title": row["title"], "year": row["year"]}
                        for row in rows]}


@router.post("/jobs", dependencies=[Depends(require_operator)])
def submit(selection: IntakeSelection, db: Session = Depends(get_db)) -> dict:
    try:
        jobs = enqueue_films(db, dataset(), selection.films)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail="Local IMDb index is unavailable or stale") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"jobs": [job_out(job) for job in sorted(jobs, key=lambda job: job.title)]}


@router.get("/jobs", dependencies=[Depends(require_operator)])
def recent_jobs(db: Session = Depends(get_db)) -> dict:
    jobs = db.scalars(select(MovieIntakeJob).order_by(MovieIntakeJob.created_at.desc()).limit(100))
    return {"jobs": [job_out(job) for job in jobs]}


@router.post("/jobs/{job_id}/retry", dependencies=[Depends(require_operator)])
def retry_job(job_id: UUID, db: Session = Depends(get_db)) -> dict:
    job = db.get(MovieIntakeJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in {"failed", "needs_review"}:
        raise HTTPException(status_code=409, detail="Only failed or review-needed jobs can be retried")
    job.status = "queued"
    job.stage = "queued"
    job.review_reason = None
    db.commit()
    return job_out(job)
