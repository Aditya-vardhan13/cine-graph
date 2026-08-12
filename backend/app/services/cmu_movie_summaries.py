"""Ingest the CC BY-SA CMU Movie Summary Corpus as a license-separated reference layer.

The archive is intentionally an explicit operator action. It is a 2012
English-Wikipedia / Freebase snapshot, so it never overwrites canonical film
facts from Wikidata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from contextlib import contextmanager
from datetime import date
from itertools import islice
from pathlib import Path
from typing import Any, Iterator

import fcntl
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import CorpusRecord, DataSource, IngestionBatch, NarrativeDocument
from app.services.wikidata import parse_date

CMU_ARCHIVE_URL = "https://www.cs.cmu.edu/~ark/personas/data/MovieSummaries.tar.gz"
CMU_SOURCE_URL = "https://www.cs.cmu.edu/~ark/personas/"
CMU_REVISION = "2012-11-02 Wikipedia plots / 2012-11-04 Freebase metadata"
CMU_LOCK_PATH = "/tmp/cinegraph-cmu-ingestion.lock"


class CmuIngestionError(RuntimeError):
    pass


@contextmanager
def exclusive_cmu_lock() -> Iterator[None]:
    with open(CMU_LOCK_PATH, "w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise CmuIngestionError("A CMU corpus ingestion is already running; wait for it to finish.") from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def source_for_cmu(db: Session) -> DataSource:
    source = db.scalar(select(DataSource).where(DataSource.name == "CMU Movie Summary Corpus"))
    if source:
        return source
    source = DataSource(
        name="CMU Movie Summary Corpus",
        url=CMU_SOURCE_URL,
        source_type="narrative_reference_corpus",
        license="CC BY-SA (source version unspecified)",
        rights_status="attribution_required",
        notes=(
            "Archive explicitly released by CMU as CC BY-SA. Plot summaries derive from the 2012 English Wikipedia dump "
            "and metadata/character alignments from 2012 Freebase. It is a historical, attributed narrative reference layer; "
            "it does not replace canonical facts."
        ),
    )
    db.add(source)
    db.flush()
    return source


def _read_member(archive: tarfile.TarFile, name: str) -> str:
    member = archive.extractfile(name)
    if member is None:
        raise CmuIngestionError(f"CMU archive is missing {name}")
    return member.read().decode("utf-8")


def _freebase_labels(value: str) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    return sorted(str(label) for label in decoded.values()) if isinstance(decoded, dict) else []


def _is_english(language_data: str) -> bool:
    return "English Language" in _freebase_labels(language_data)


def archive_rows(archive_path: Path, limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Yield CMU English records with a plot, preserving source fields unmodified."""
    with tarfile.open(archive_path, "r:gz") as archive:
        plots = {
            line.partition("\t")[0]: line.partition("\t")[2].strip()
            for line in _read_member(archive, "MovieSummaries/plot_summaries.txt").splitlines()
            if "\t" in line
        }
        published = 0
        for line in _read_member(archive, "MovieSummaries/movie.metadata.tsv").splitlines():
            parts = line.split("\t")
            if len(parts) != 9 or not _is_english(parts[6]) or not plots.get(parts[0]):
                continue
            yield {
                "wikipedia_movie_id": parts[0],
                "freebase_movie_id": parts[1],
                "title": parts[2],
                "release_date": parse_date(parts[3]),
                "languages": _freebase_labels(parts[6]),
                "countries": _freebase_labels(parts[7]),
                "genres": _freebase_labels(parts[8]),
                "box_office": parts[4] or None,
                "runtime_minutes": parts[5] or None,
                "plot": plots[parts[0]],
            }
            published += 1
            if limit is not None and published >= limit:
                return


def chunked(rows: Iterator[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    """Yield bounded pages so the full archive can be committed safely."""
    while page := list(islice(rows, size)):
        yield page


def ingest_archive(
    db: Session,
    archive_path: Path,
    limit: int | None = None,
    page_size: int = 250,
) -> IngestionBatch:
    if not archive_path.is_file():
        raise CmuIngestionError(f"Archive not found: {archive_path}")
    if page_size < 1:
        raise CmuIngestionError("page_size must be positive")
    with exclusive_cmu_lock():
        source = source_for_cmu(db)
        batch = IngestionBatch(
            source_id=source.id,
            external_reference=CMU_ARCHIVE_URL,
            status="running",
        )
        db.add(batch)
        db.flush()
        received = published = 0
        try:
            for page in chunked(archive_rows(archive_path, limit), page_size):
                external_ids = [row["wikipedia_movie_id"] for row in page]
                records = {
                    record.external_id: record
                    for record in db.scalars(select(CorpusRecord).where(
                        CorpusRecord.source_id == source.id,
                        CorpusRecord.external_id.in_(external_ids),
                    ))
                }
                for row in page:
                    if row["wikipedia_movie_id"] in records:
                        continue
                    record = CorpusRecord(
                        source_id=source.id,
                        external_id=row["wikipedia_movie_id"],
                        title=row["title"],
                        release_date=row["release_date"],
                        language_codes=row["languages"],
                        country_codes=row["countries"],
                        genres=row["genres"],
                        source_revision=CMU_REVISION,
                        raw_metadata={
                            "freebase_movie_id": row["freebase_movie_id"],
                            "box_office": row["box_office"],
                            "runtime_minutes": row["runtime_minutes"],
                        },
                    )
                    db.add(record)
                    records[row["wikipedia_movie_id"]] = record
                db.flush()

                document_keys = {
                    (corpus_record_id, content_hash)
                    for corpus_record_id, content_hash in db.execute(select(
                        NarrativeDocument.corpus_record_id,
                        NarrativeDocument.content_hash,
                    ).where(
                        NarrativeDocument.corpus_record_id.in_(record.id for record in records.values()),
                        NarrativeDocument.document_type == "plot_summary",
                    ))
                }
                for row in page:
                    record = records[row["wikipedia_movie_id"]]
                    content_hash = hashlib.sha256(row["plot"].encode("utf-8")).hexdigest()
                    if (record.id, content_hash) in document_keys:
                        continue
                    db.add(NarrativeDocument(
                        corpus_record_id=record.id,
                        document_type="plot_summary",
                        language_code="en",
                        content=row["plot"],
                        content_hash=content_hash,
                        license="CC BY-SA (source version unspecified)",
                        attribution_url=f"https://en.wikipedia.org/?curid={row['wikipedia_movie_id']}",
                        source_revision=CMU_REVISION,
                    ))
                received += len(page)
                published += len(page)
                batch.records_received = received
                batch.records_published = published
                batch.records_rejected = 0
                db.commit()
                print(f"CMU checkpoint: {published} English plot records", flush=True)

            batch.status = "complete"
            db.commit()
            return batch
        except Exception:
            db.rollback()
            failed_batch = db.get(IngestionBatch, batch.id)
            if failed_batch:
                failed_batch.status = "failed"
                db.commit()
            raise


def download_archive(destination: Path) -> None:
    headers = {
        "User-Agent": get_settings().wikidata_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }
    with httpx.Client(timeout=180, headers=headers, follow_redirects=True) as client:
        response = client.get(CMU_ARCHIVE_URL)
    response.raise_for_status()
    destination.write_bytes(response.content)


def main() -> None:
    from app.db import Base, SessionLocal, engine

    parser = argparse.ArgumentParser(description="Ingest the CC BY-SA CMU Movie Summary Corpus as an attributed narrative layer.")
    parser.add_argument("--archive", type=Path, help="Downloaded MovieSummaries.tar.gz archive")
    parser.add_argument("--download-to", type=Path, help="Explicitly download the archive to this path before ingesting")
    parser.add_argument("--limit", type=int, help="Temporary validation limit; do not use as a production sampling strategy")
    parser.add_argument("--page-size", type=int, default=250, help="Checkpoint interval for a resumable bulk import")
    args = parser.parse_args()
    if bool(args.archive) == bool(args.download_to):
        parser.error("Provide exactly one of --archive or --download-to")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    if args.page_size < 1:
        parser.error("--page-size must be positive")
    archive_path = args.archive or args.download_to
    assert archive_path is not None
    if args.download_to:
        download_archive(archive_path)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        batch = ingest_archive(db, archive_path, args.limit, args.page_size)
        print(f"Completed CMU batch {batch.id}: {batch.records_published} English plot records")


if __name__ == "__main__":
    main()
