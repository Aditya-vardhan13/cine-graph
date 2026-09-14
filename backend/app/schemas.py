from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProvenanceOut(BaseModel):
    source_name: str
    source_url: str
    license: str
    field_name: str
    source_reference: str


class CreditOut(BaseModel):
    person_id: UUID
    name: str
    role: str
    character_name: str | None = None


class FilmListItem(BaseModel):
    id: UUID
    title: str
    release_date: date | None
    runtime_minutes: int | None
    genres: list[str]
    language_code: str


class FilmDetail(FilmListItem):
    wikidata_id: str | None
    countries: list[str]
    aliases: list[str]
    credits: list[CreditOut]
    provenance: list[ProvenanceOut]


class PersonDetail(BaseModel):
    id: UUID
    name: str
    wikidata_id: str | None
    aliases: list[str]
    films: list[FilmListItem]
    provenance: list[ProvenanceOut]


class GraphNode(BaseModel):
    id: str
    label: str
    type: str


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str
    evidence: str


class GraphOut(BaseModel):
    center_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool


class SimilarityFactor(BaseModel):
    label: str
    weight: float
    contribution: float
    evidence: str


class SimilarFilmOut(FilmListItem):
    score: float = Field(ge=0, le=100)
    factors: list[SimilarityFactor]


class FilmComparison(BaseModel):
    first: FilmListItem
    second: FilmListItem
    summary: str
    signals: list[SimilarityFactor]


class ResearchFilmOut(BaseModel):
    entity_id: UUID
    film_id: UUID | None
    title: str
    release_date: date | None
    runtime_minutes: int | None
    genres: list[str]
    language_code: str


class StoryComparisonRequest(BaseModel):
    first_entity_id: UUID
    second_entity_id: UUID
    question: str = Field(min_length=12, max_length=400)
    retrieval_method: Literal["hybrid", "lexical"] = "hybrid"


class StoryComparisonEvidenceOut(BaseModel):
    chunk_id: str
    section_title: str
    section_locator: str
    excerpt: str
    source_url: str
    source_revision: str | None
    source_license: str
    matched_by: list[str]


class StoryComparisonLensOut(BaseModel):
    identifier: str
    label: str
    research_question: str
    writer_prompt: str
    first_evidence: StoryComparisonEvidenceOut | None
    second_evidence: StoryComparisonEvidenceOut | None


class StoryComparisonOut(BaseModel):
    question: str
    first: ResearchFilmOut
    second: ResearchFilmOut
    requested_method: str
    retrieval_method: str
    degraded: bool
    fallback_reason: str | None
    summary: str
    caution: str
    lenses: list[StoryComparisonLensOut]


class LineageEdgeOut(BaseModel):
    assertion_id: UUID
    predicate: str
    relation_label: str
    direction: str
    target_id: UUID
    target_title: str
    target_kind: str
    target_film: FilmListItem | None = None
    writer_question: str
    evidence_url: str | None
    assertion_kind: str


class FilmLineageOut(BaseModel):
    film: FilmListItem
    summary: str
    edges: list[LineageEdgeOut]


class LanguageEditionOut(BaseModel):
    code: str
    display_name: str
    native_name: str | None
    script: str
    enabled: bool
    status: str
    transliteration_strategy: str | None


class HealthOut(BaseModel):
    status: str
    films: int
    people: int
    credits: int
    sources: int
    latest_ingestion_at: datetime | None
    language_editions: list[LanguageEditionOut]


class CorpusSourceQuality(BaseModel):
    source_name: str
    license: str
    records: int
    matched: int
    review_required: int
    narrative_documents: int


class CorpusQualityOut(BaseModel):
    films: int
    release_events: int
    explicit_work_relationships: int
    sources: list[CorpusSourceQuality]
