"""Build licensed, reproducible narrative evidence chunks before embeddings.

This module has one job: convert already-retained narrative passages into a
small, source-linked retrieval unit.  It deliberately does not label themes,
infer relationships, or write canonical facts.  Those are separate, reviewable
steps after a vector model is evaluated.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable
from uuid import uuid4

import spacy
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import (
    EvidenceChunk,
    EvidenceChunkRun,
    NarrativePassage,
    ReferenceCollection,
    ReferenceCollectionMembership,
    SourceSnapshot,
)


CHUNKER_VERSION = "spacy-sentencizer-evidence-v3"
NORMALIZATION_VERSION = "unicode-nfc-whitespace-v1"
ALLOWED_NARRATIVE_LICENSES = {"CC BY-SA 4.0"}
WORD = re.compile(r"\b[\w'-]+\b", re.UNICODE)


@dataclass(frozen=True)
class ChunkConfiguration:
    """Versioned policy, separate from the future embedding tokenizer/model."""

    target_tokens: int = 300
    maximum_tokens: int = 360
    overlap_tokens: int = 50
    minimum_words: int = 40
    normalization_version: str = NORMALIZATION_VERSION

    def __post_init__(self) -> None:
        if not (0 < self.minimum_words <= self.target_tokens <= self.maximum_tokens):
            raise ValueError("Chunk sizes must satisfy 0 < minimum_words <= target_tokens <= maximum_tokens.")
        if self.overlap_tokens < 0 or self.overlap_tokens >= self.target_tokens:
            raise ValueError("overlap_tokens must be non-negative and smaller than target_tokens.")

    @property
    def payload(self) -> dict[str, int | str]:
        return asdict(self)

    @property
    def digest(self) -> str:
        encoded = json.dumps(self.payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Sentence:
    content: str
    token_count: int


@dataclass(frozen=True)
class PreparedChunk:
    ordinal: int
    content: str
    content_hash: str
    word_count: int
    token_count_estimate: int
    sentence_count: int
    quality_status: str
    quality_flags: tuple[str, ...]


def normalize_content(value: str) -> str:
    """Normalise presentation noise without changing the source passage itself."""
    return " ".join(unicodedata.normalize("NFC", value).split())


def _english_pipeline():
    pipeline = spacy.blank("en")
    pipeline.add_pipe("sentencizer")
    return pipeline


_ENGLISH_PIPELINE = _english_pipeline()


def sentences_for(value: str, *, language_code: str = "en") -> list[Sentence]:
    """Use spaCy's model-free sentencizer so no trained NLP model is hidden here."""
    if language_code != "en":
        raise ValueError(f"No sentence segmenter is registered for language {language_code!r}.")
    document = _ENGLISH_PIPELINE(normalize_content(value))
    sentences = [
        Sentence(
            content=sentence.text.strip(),
            token_count=sum(1 for token in sentence if not token.is_space),
        )
        for sentence in document.sents
        if sentence.text.strip()
    ]
    return sentences


def _overlap(sentences: list[Sentence], overlap_tokens: int) -> list[Sentence]:
    if not sentences or overlap_tokens == 0:
        return []
    selected: list[Sentence] = []
    total = 0
    for sentence in reversed(sentences):
        selected.append(sentence)
        total += sentence.token_count
        if total >= overlap_tokens:
            break
    return list(reversed(selected))


def _prepared_chunk(ordinal: int, source_sentences: list[Sentence], config: ChunkConfiguration) -> PreparedChunk:
    content = normalize_content(" ".join(sentence.content for sentence in source_sentences))
    token_count = sum(sentence.token_count for sentence in source_sentences)
    word_count = len(WORD.findall(content))
    flags: list[str] = []
    if word_count < config.minimum_words:
        flags.append("below_minimum_words")
    if any(sentence.token_count > config.maximum_tokens for sentence in source_sentences):
        flags.append("oversized_single_sentence")
    # The configured maximum is an embedding-input contract, not a suggestion.
    # We preserve an oversized sentence for audit and later specialised handling,
    # but it cannot silently enter the first vector index.
    status = "excluded" if {"below_minimum_words", "oversized_single_sentence"}.intersection(flags) else "eligible"
    return PreparedChunk(
        ordinal=ordinal,
        content=content,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        word_count=word_count,
        token_count_estimate=token_count,
        sentence_count=len(source_sentences),
        quality_status=status,
        quality_flags=tuple(flags),
    )


def chunk_passage(value: str, *, language_code: str = "en", config: ChunkConfiguration | None = None) -> list[PreparedChunk]:
    """Split only at sentence boundaries with bounded overlap and explicit flags.

    A sentence larger than the maximum is kept intact rather than cut mid-claim;
    it is retained as excluded evidence until a separately versioned long-form
    policy can handle it without changing this index contract.
    """
    config = config or ChunkConfiguration()
    source_sentences = sentences_for(value, language_code=language_code)
    if not source_sentences:
        return []

    chunks: list[PreparedChunk] = []
    current: list[Sentence] = []
    current_tokens = 0
    for sentence in source_sentences:
        if current and current_tokens >= config.target_tokens:
            chunks.append(_prepared_chunk(len(chunks), current, config))
            current = _overlap(current, config.overlap_tokens)
            current_tokens = sum(item.token_count for item in current)
        if current and current_tokens + sentence.token_count > config.maximum_tokens:
            chunks.append(_prepared_chunk(len(chunks), current, config))
            current = _overlap(current, config.overlap_tokens)
            current_tokens = sum(item.token_count for item in current)
            # An overlap is useful only when it still honours the input bound.
            # Keep the next whole sentence by itself rather than producing an
            # over-limit eligible chunk or splitting its evidence mid-sentence.
            if current and current_tokens + sentence.token_count > config.maximum_tokens:
                current = []
                current_tokens = 0
        current.append(sentence)
        current_tokens += sentence.token_count
    if current:
        chunks.append(_prepared_chunk(len(chunks), current, config))
    return chunks


def _collection(db: Session, collection_code: str, language_code: str) -> ReferenceCollection:
    collection = db.get(ReferenceCollection, collection_code)
    if collection is None:
        raise ValueError(f"Unknown reference collection {collection_code!r}; create its explicit membership boundary first.")
    if collection.language_code != language_code:
        raise ValueError(
            f"Collection {collection_code!r} is configured for {collection.language_code!r}, not {language_code!r}."
        )
    return collection


def _run_for(
    db: Session,
    *,
    collection_code: str,
    language_code: str,
    config: ChunkConfiguration,
) -> EvidenceChunkRun:
    run = db.scalar(select(EvidenceChunkRun).where(
        EvidenceChunkRun.collection_code == collection_code,
        EvidenceChunkRun.language_code == language_code,
        EvidenceChunkRun.chunker_version == CHUNKER_VERSION,
        EvidenceChunkRun.configuration_hash == config.digest,
    ))
    if run is not None:
        return run
    run = EvidenceChunkRun(
        collection_code=collection_code,
        language_code=language_code,
        chunker_version=CHUNKER_VERSION,
        configuration=config.payload,
        configuration_hash=config.digest,
        status="running",
    )
    db.add(run)
    db.flush()
    return run


def _passages_for_collection(
    db: Session,
    *,
    collection_code: str,
    language_code: str,
) -> list[tuple[NarrativePassage, str, str | None]]:
    rows = db.execute(
        select(NarrativePassage, SourceSnapshot.license, SourceSnapshot.attribution_url)
        .join(SourceSnapshot, SourceSnapshot.id == NarrativePassage.source_snapshot_id)
        .join(ReferenceCollectionMembership, ReferenceCollectionMembership.entity_id == NarrativePassage.subject_entity_id)
        .where(
            ReferenceCollectionMembership.collection_code == collection_code,
            ReferenceCollectionMembership.status == "included",
            NarrativePassage.language_code == language_code,
        )
        .order_by(
            NarrativePassage.subject_entity_id,
            NarrativePassage.source_snapshot_id,
            NarrativePassage.section_locator,
            NarrativePassage.ordinal,
        )
    ).all()
    return [(passage, license, attribution_url) for passage, license, attribution_url in rows]


def build_evidence_chunks(
    db: Session,
    *,
    collection_code: str,
    language_code: str = "en",
    config: ChunkConfiguration | None = None,
) -> dict[str, int | str]:
    """Materialise the collection exactly once per versioned configuration.

    Existing rows are reused, and exact duplicate text remains represented with
    its own source lineage but points to a canonical eligible chunk.  Nothing
    is silently discarded.
    """
    config = config or ChunkConfiguration()
    _collection(db, collection_code, language_code)
    run = _run_for(db, collection_code=collection_code, language_code=language_code, config=config)
    passages = _passages_for_collection(db, collection_code=collection_code, language_code=language_code)
    existing = {
        (item.narrative_passage_id, item.chunk_ordinal): item
        for item in db.scalars(select(EvidenceChunk).where(
            EvidenceChunk.preprocessing_run_id == run.id,
            EvidenceChunk.chunker_version == CHUNKER_VERSION,
            EvidenceChunk.configuration_hash == config.digest,
        ))
    }
    canonical_by_hash = {
        item.content_hash: item.id
        for item in existing.values()
        if item.quality_status == "eligible"
    }

    created = reused = excluded = passages_eligible = 0
    try:
        for passage, license_name, attribution_url in passages:
            if license_name not in ALLOWED_NARRATIVE_LICENSES or not attribution_url:
                continue
            passages_eligible += 1
            for prepared in chunk_passage(passage.content, language_code=language_code, config=config):
                key = (passage.id, prepared.ordinal)
                if key in existing:
                    reused += 1
                    continue
                status = prepared.quality_status
                duplicate_of_chunk_id = None
                flags = list(prepared.quality_flags)
                if status == "eligible" and prepared.content_hash in canonical_by_hash:
                    status = "duplicate"
                    duplicate_of_chunk_id = canonical_by_hash[prepared.content_hash]
                    flags.append("exact_duplicate_content")
                chunk = EvidenceChunk(
                    id=uuid4(),
                    preprocessing_run_id=run.id,
                    narrative_passage_id=passage.id,
                    subject_entity_id=passage.subject_entity_id,
                    source_snapshot_id=passage.source_snapshot_id,
                    language_code=language_code,
                    section_locator=passage.section_locator,
                    section_title=passage.section_title,
                    chunk_ordinal=prepared.ordinal,
                    content=prepared.content,
                    content_hash=prepared.content_hash,
                    word_count=prepared.word_count,
                    token_count_estimate=prepared.token_count_estimate,
                    sentence_count=prepared.sentence_count,
                    quality_status=status,
                    quality_flags=flags,
                    duplicate_of_chunk_id=duplicate_of_chunk_id,
                    chunker_version=CHUNKER_VERSION,
                    configuration_hash=config.digest,
                )
                db.add(chunk)
                existing[key] = chunk
                if status == "eligible":
                    canonical_by_hash[prepared.content_hash] = chunk.id
                if status == "excluded":
                    excluded += 1
                created += 1
        run.status = "complete"
        run.passages_requested = len(passages)
        run.passages_eligible = passages_eligible
        run.chunks_created = created
        run.chunks_reused = reused
        run.chunks_excluded = excluded
        run.error_summary = None
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        # A subsequent invocation resumes against the same deterministic key;
        # keep the original rows, but make failure visible if the run survived.
        persisted = db.get(EvidenceChunkRun, run.id)
        if persisted is not None:
            persisted.status = "failed"
            persisted.error_summary = str(exc)[:2000]
            db.commit()
        raise

    return {
        "run_id": str(run.id),
        "collection_code": collection_code,
        "passages_requested": len(passages),
        "passages_eligible": passages_eligible,
        "chunks_created": created,
        "chunks_reused": reused,
        "chunks_excluded": excluded,
    }


def evidence_chunk_quality_report(
    db: Session,
    *,
    collection_code: str,
    language_code: str = "en",
    config: ChunkConfiguration | None = None,
) -> dict[str, object]:
    """Return a compact, auditable readiness report without loading an ML model."""
    config = config or ChunkConfiguration()
    run = db.scalar(select(EvidenceChunkRun).where(
        EvidenceChunkRun.collection_code == collection_code,
        EvidenceChunkRun.language_code == language_code,
        EvidenceChunkRun.chunker_version == CHUNKER_VERSION,
        EvidenceChunkRun.configuration_hash == config.digest,
    ))
    if run is None:
        raise ValueError("No evidence-chunk run exists for this exact collection and configuration.")
    chunks = list(db.scalars(select(EvidenceChunk).where(EvidenceChunk.preprocessing_run_id == run.id)))
    status_counts = Counter(chunk.quality_status for chunk in chunks)
    flags = Counter(flag for chunk in chunks for flag in chunk.quality_flags)
    chunks_per_film = Counter(chunk.subject_entity_id for chunk in chunks if chunk.quality_status == "eligible")
    token_counts = [chunk.token_count_estimate for chunk in chunks if chunk.quality_status == "eligible"]
    return {
        "run_id": str(run.id),
        "status": run.status,
        "collection_code": collection_code,
        "chunker_version": run.chunker_version,
        "configuration": run.configuration,
        "passages_requested": run.passages_requested,
        "passages_eligible": run.passages_eligible,
        "chunk_count": len(chunks),
        "quality_status_counts": dict(sorted(status_counts.items())),
        "quality_flag_counts": dict(sorted(flags.items())),
        "eligible_chunks_per_film": {
            "min": min(chunks_per_film.values(), default=0),
            "max": max(chunks_per_film.values(), default=0),
            "films_with_eligible_chunks": len(chunks_per_film),
        },
        "eligible_token_count_estimate": {
            "min": min(token_counts, default=0),
            "max": max(token_counts, default=0),
            "average": round(sum(token_counts) / len(token_counts), 2) if token_counts else 0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build or inspect CineGraph's versioned narrative evidence chunks.")
    parser.add_argument("--collection", required=True, help="Explicit reference collection code; no inferred membership.")
    parser.add_argument("--language", default="en")
    parser.add_argument("--build", action="store_true", help="Materialise source-linked chunks for the configured collection.")
    parser.add_argument("--report", action="store_true", help="Print the readiness report for the exact configured run.")
    arguments = parser.parse_args()
    if not arguments.build and not arguments.report:
        parser.error("Specify at least one of --build or --report.")
    with SessionLocal() as db:
        if arguments.build:
            print(json.dumps(build_evidence_chunks(db, collection_code=arguments.collection, language_code=arguments.language), indent=2))
        if arguments.report:
            print(json.dumps(evidence_chunk_quality_report(db, collection_code=arguments.collection, language_code=arguments.language), indent=2))


if __name__ == "__main__":
    main()
