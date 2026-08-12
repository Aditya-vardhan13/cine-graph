from datetime import date, datetime
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
