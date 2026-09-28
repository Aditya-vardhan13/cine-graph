"""Evidence workbench for comparing two films through a writer's question.

This application use case retrieves attributable passages and arranges them
side by side. It deliberately does not turn semantic proximity into a fact or
silently generate an interpretation. A later synthesis adapter may consume
this contract, but must preserve every evidence pointer and label its output as
interpretation.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID

import httpx
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session

from app.models import EvidenceChunk, SourceSnapshot
from app.services.comparison_answerability import substantive_question_terms, unmet_source_requirement
from app.services.hybrid_evidence_retrieval import (
    HybridRetrievedEvidence,
    HybridRetrievalResult,
    NarrativeRetrievalMethod,
    embed_narrative_queries,
    retrieve_narrative_candidates,
)
from app.services.ollama_embeddings import OllamaEmbeddingClient
from app.services.research_catalog import DEFAULT_RESEARCH_COLLECTION, ResearchFilm, get_research_film
from app.services.retrieval_scope import resolve_retrieval_scope


@dataclass(frozen=True)
class ComparisonLensDefinition:
    identifier: str
    label: str
    question_id: str
    query_template: str
    writer_prompt: str

    def query(self, focus: str) -> str:
        return self.query_template.format(focus=focus.strip())


COMPARISON_LENSES = (
    ComparisonLensDefinition(
        identifier="central_question",
        label="Central question",
        question_id="story.writer_focus",
        query_template="{focus}",
        writer_prompt=(
            "Name the dramatic promise both films engage, then identify what each "
            "protagonist risks losing by answering it differently."
        ),
    ),
    ComparisonLensDefinition(
        identifier="story_engine",
        label="Story engine",
        question_id="story.plot_character_structure",
        query_template=(
            "In relation to '{focus}', what central conflict, escalation, turning "
            "point, and ending consequence drive this film?"
        ),
        writer_prompt=(
            "Compare the chain of pressure and consequence, not merely the films' "
            "shared subject matter."
        ),
    ),
    ComparisonLensDefinition(
        identifier="character_change",
        label="Character change",
        question_id="character.transformation",
        query_template=(
            "In relation to '{focus}', how do the protagonist's needs, choices, "
            "relationships, and transformation develop?"
        ),
        writer_prompt=(
            "Ask which choice changes the character, and whether the ending rewards, "
            "punishes, or complicates that change."
        ),
    ),
    ComparisonLensDefinition(
        identifier="craft_treatment",
        label="Craft treatment",
        question_id="craft.execution",
        query_template=(
            "In relation to '{focus}', which writing, production, visual, editing, "
            "sound, or performance choices shaped the treatment?"
        ),
        writer_prompt=(
            "Separate the underlying idea from the craft decisions that make each "
            "version feel different on screen."
        ),
    ),
    ComparisonLensDefinition(
        identifier="reception_legacy",
        label="Reception and legacy",
        question_id="reception.legacy",
        query_template=(
            "In relation to '{focus}', how was this treatment received, interpreted, "
            "debated, or influential?"
        ),
        writer_prompt=(
            "Treat reception as attributed context: it can reveal what audiences read "
            "in the work, but it is not a universal verdict."
        ),
    ),
)


_RECEPTION_FOCUS = re.compile(r"\b(?:critics?|reviewers?|reviews?|reception|critical response)\b", re.I)
_CRAFT_FOCUS = re.compile(
    r"\b(?:visuals?|cinematography|camerawork|camera|editing|lighting|music|score|"
    r"soundtrack|sound design|visual effects|special effects|practical effects|"
    r"digital effects|image choices|production design|choreography|performance choices)\b",
    re.I,
)


def focus_evidence_question_id(question: str) -> str:
    """Choose a source section by evidence kind, not a film-specific topic cue."""
    if _RECEPTION_FOCUS.search(question):
        return "reception.writer_focus"
    if _CRAFT_FOCUS.search(question):
        return "craft.writer_focus"
    return "story.writer_focus"


@dataclass(frozen=True)
class ComparisonEvidence:
    chunk_id: str
    section_title: str
    section_locator: str
    excerpt: str
    source_url: str
    source_revision: str | None
    source_license: str
    matched_by: tuple[str, ...]


@dataclass(frozen=True)
class ComparisonLensResult:
    identifier: str
    label: str
    research_question: str
    writer_prompt: str
    first_evidence: ComparisonEvidence | None
    second_evidence: ComparisonEvidence | None
    first_options: tuple[ComparisonEvidence, ...]
    second_options: tuple[ComparisonEvidence, ...]


@dataclass(frozen=True)
class StoryComparisonResult:
    question: str
    first: ResearchFilm
    second: ResearchFilm
    requested_method: str
    retrieval_method: str
    degraded: bool
    fallback_reason: str | None
    summary: str
    caution: str
    answerability_status: str
    answerability_reason: str | None
    lenses: tuple[ComparisonLensResult, ...]
    preprocessing_run_id: str
    index_run_id: str | None


def _source_details(
    db: Session, evidence: list[HybridRetrievedEvidence],
) -> dict[str, tuple[str, str | None, str]]:
    snapshot_ids = {UUID(item.source_snapshot_id) for item in evidence}
    if not snapshot_ids:
        return {}
    snapshots = db.scalars(select(SourceSnapshot).where(SourceSnapshot.id.in_(snapshot_ids))).all()
    return {
        str(snapshot.id): (
            snapshot.attribution_url or snapshot.canonical_url,
            snapshot.source_revision,
            snapshot.license,
        )
        for snapshot in snapshots
    }


def _first_unique(
    candidates: tuple[HybridRetrievedEvidence, ...], used_contents: set[str],
) -> HybridRetrievedEvidence | None:
    for candidate in candidates:
        content = " ".join(candidate.content.split()).casefold()
        if content not in used_contents:
            used_contents.add(content)
            return candidate
    return None


def _evidence_dto(
    item: HybridRetrievedEvidence | None,
    source_details: dict[str, tuple[str, str | None, str]],
) -> ComparisonEvidence | None:
    if item is None:
        return None
    source_url, source_revision, source_license = source_details[item.source_snapshot_id]
    return ComparisonEvidence(
        chunk_id=item.chunk_id,
        section_title=item.section_title,
        section_locator=item.section_locator,
        excerpt=item.content,
        source_url=source_url,
        source_revision=source_revision,
        source_license=source_license,
        matched_by=item.matched_by,
    )


def _evidence_options(
    primary: HybridRetrievedEvidence | None,
    candidates: tuple[HybridRetrievedEvidence, ...],
    source_details: dict[str, tuple[str, str | None, str]],
) -> tuple[ComparisonEvidence, ...]:
    """Expose distinct, attributable alternatives without changing the default ranking."""
    if primary is None:
        return ()
    seen: set[str] = set()
    options: list[ComparisonEvidence] = []
    for item in (primary, *candidates):
        normalized = " ".join(item.content.split()).casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        option = _evidence_dto(item, source_details)
        if option is not None:
            options.append(option)
    return tuple(options)


def _both_films_have_question_anchor(
    db: Session, *, question: str, first: ResearchFilm, second: ResearchFilm, preprocessing_run_id: UUID,
) -> bool:
    terms = substantive_question_terms(question, first.title, second.title)
    if not terms:
        return False
    english = literal_column("'english'::regconfig")
    query = func.to_tsquery(english, " | ".join(terms))
    document = func.to_tsvector(english, EvidenceChunk.section_title + " " + EvidenceChunk.content)
    matched_subjects = set(db.scalars(select(EvidenceChunk.subject_entity_id).where(
        EvidenceChunk.preprocessing_run_id == preprocessing_run_id,
        EvidenceChunk.subject_entity_id.in_((first.entity_id, second.entity_id)),
        EvidenceChunk.quality_status == "eligible",
        document.op("@@")(query),
    ).distinct()).all())
    return first.entity_id in matched_subjects and second.entity_id in matched_subjects


def compare_story_evidence(
    db: Session,
    *,
    first_entity_id: UUID,
    second_entity_id: UUID,
    question: str,
    requested_method: NarrativeRetrievalMethod = NarrativeRetrievalMethod.HYBRID,
    embedding_client: OllamaEmbeddingClient | None = None,
    collection_code: str = DEFAULT_RESEARCH_COLLECTION,
) -> StoryComparisonResult:
    """Retrieve five distinct, attributable evidence lenses for two films."""
    if first_entity_id == second_entity_id:
        raise ValueError("Choose two different films to compare.")
    first = get_research_film(db, first_entity_id, collection_code=collection_code)
    second = get_research_film(db, second_entity_id, collection_code=collection_code)
    if first is None or second is None:
        raise LookupError("One or both films are unavailable for narrative comparison.")

    actual_method = requested_method
    fallback_reason: str | None = None
    scope = resolve_retrieval_scope(db, collection_code=collection_code)
    requirement = unmet_source_requirement(question)
    if requirement is not None:
        return StoryComparisonResult(
            question=question.strip(), first=first, second=second,
            requested_method=requested_method.value,
            retrieval_method="not_run", degraded=False, fallback_reason=None,
            summary="Current sources cannot substantiate this question.",
            caution="No film relationship or factual conclusion was inferred from unrelated passages.",
            answerability_status="insufficient_evidence",
            answerability_reason=requirement.explanation,
            lenses=(), preprocessing_run_id=str(scope.preprocessing_run_id), index_run_id=None,
        )
    if not _both_films_have_question_anchor(
        db, question=question, first=first, second=second,
        preprocessing_run_id=scope.preprocessing_run_id,
    ):
        return StoryComparisonResult(
            question=question.strip(), first=first, second=second,
            requested_method=requested_method.value,
            retrieval_method="not_run", degraded=False, fallback_reason=None,
            summary="No two-sided source lead matches this writing question yet.",
            caution="A missing term match does not prove the films lack this idea; try another phrasing or source.",
            answerability_status="insufficient_evidence",
            answerability_reason="Both selected films need a current passage that directly mentions a substantive term in your question.",
            lenses=(), preprocessing_run_id=str(scope.preprocessing_run_id), index_run_id=None,
        )

    def retrieve_all(
        method: NarrativeRetrievalMethod,
    ) -> list[tuple[ComparisonLensDefinition, str, HybridRetrievalResult, HybridRetrievalResult]]:
        research_questions = [lens.query(question) for lens in COMPARISON_LENSES]
        query_vectors: tuple[list[float], ...] | tuple[None, ...]
        if method == NarrativeRetrievalMethod.HYBRID:
            query_vectors = embed_narrative_queries(
                db,
                question_texts=research_questions,
                client=embedding_client,
                scope=scope,
            )
        else:
            query_vectors = (None,) * len(research_questions)
        rows = []
        for lens, research_question, query_vector in zip(
            COMPARISON_LENSES, research_questions, query_vectors, strict=True,
        ):
            question_id = (focus_evidence_question_id(question) if lens.identifier == "central_question"
                           else lens.question_id)
            first_result = retrieve_narrative_candidates(
                db,
                subject_entity_id=first.entity_id,
                question_id=question_id,
                question_text=research_question,
                method=method,
                limit=3,
                candidate_limit=30,
                client=embedding_client,
                query_vector=query_vector,
                scope=scope,
            )
            second_result = retrieve_narrative_candidates(
                db,
                subject_entity_id=second.entity_id,
                question_id=question_id,
                question_text=research_question,
                method=method,
                limit=3,
                candidate_limit=30,
                client=embedding_client,
                query_vector=query_vector,
                scope=scope,
            )
            rows.append((lens, research_question, first_result, second_result))
        return rows

    try:
        retrieved = retrieve_all(requested_method)
    except (ValueError, httpx.HTTPError, RuntimeError):
        if requested_method == NarrativeRetrievalMethod.LEXICAL:
            raise
        actual_method = NarrativeRetrievalMethod.LEXICAL
        fallback_reason = (
            "The local semantic index or embedding service was unavailable; "
            "results use attributable lexical retrieval only."
        )
        retrieved = retrieve_all(actual_method)

    all_evidence = [
        evidence
        for _, _, first_result, second_result in retrieved
        for result in (first_result, second_result)
        for evidence in result.evidence
    ]
    source_details = _source_details(db, all_evidence)
    used_first: set[str] = set()
    used_second: set[str] = set()
    lenses_list: list[ComparisonLensResult] = []
    for lens, research_question, first_result, second_result in retrieved:
        first_primary = _first_unique(first_result.evidence, used_first)
        second_primary = _first_unique(second_result.evidence, used_second)
        lenses_list.append(ComparisonLensResult(
            identifier=lens.identifier,
            label=lens.label,
            research_question=research_question,
            writer_prompt=lens.writer_prompt,
            first_evidence=_evidence_dto(first_primary, source_details),
            second_evidence=_evidence_dto(second_primary, source_details),
            first_options=_evidence_options(first_primary, first_result.evidence, source_details),
            second_options=_evidence_options(second_primary, second_result.evidence, source_details),
        ))
    lenses = tuple(lenses_list)
    paired = sum(1 for lens in lenses if lens.first_evidence and lens.second_evidence)
    has_pair = paired > 0
    return StoryComparisonResult(
        question=question.strip(),
        first=first,
        second=second,
        requested_method=requested_method.value,
        retrieval_method=actual_method.value,
        degraded=actual_method != requested_method,
        fallback_reason=fallback_reason,
        summary=(
            f"{paired} paired research lead{'s' if paired != 1 else ''} found; relevance needs review."
            if has_pair else "No paired source passage was found for this question."
        ),
        caution=(
            "Passages are attributable source evidence, not automatically proven similarities. "
            "The prompts identify what a writer should compare without promoting an interpretation to fact."
        ),
        answerability_status="candidate_evidence" if has_pair else "insufficient_evidence",
        answerability_reason=None if has_pair else "The selected films do not have a two-sided evidence lead in the current source collection.",
        lenses=lenses if has_pair else (),
        preprocessing_run_id=str(scope.preprocessing_run_id),
        index_run_id=str(scope.index_run.id) if scope.index_run and actual_method != NarrativeRetrievalMethod.LEXICAL else None,
    )
