"""Deterministic lexical retrieval policies for source-linked evidence."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable


TOKEN = re.compile(r"\b[\w'-]+\b", re.UNICODE)


def tokenize(value: str) -> list[str]:
    return [token.casefold() for token in TOKEN.findall(value)]


@dataclass(frozen=True)
class Bm25Index:
    """Small in-process BM25 reference implementation for model evaluation."""

    documents: tuple[Counter[str], ...]
    document_lengths: tuple[int, ...]
    inverse_document_frequency: dict[str, float]
    average_document_length: float
    k1: float = 1.5
    b: float = 0.75

    @classmethod
    def build(cls, values: Iterable[str]) -> "Bm25Index":
        documents = tuple(Counter(tokenize(value)) for value in values)
        document_lengths = tuple(sum(document.values()) for document in documents)
        document_frequency = Counter(term for document in documents for term in document)
        count = len(documents)
        idf = {
            term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }
        return cls(
            documents=documents,
            document_lengths=document_lengths,
            inverse_document_frequency=idf,
            average_document_length=(sum(document_lengths) / count) if count else 0.0,
        )

    def scores(self, query: str) -> list[float]:
        terms = Counter(tokenize(query))
        if not self.documents or not terms or not self.average_document_length:
            return [0.0] * len(self.documents)
        scores: list[float] = []
        for document, length in zip(self.documents, self.document_lengths, strict=True):
            normalizer = self.k1 * (1 - self.b + self.b * length / self.average_document_length)
            score = 0.0
            for term, query_count in terms.items():
                frequency = document.get(term, 0)
                if frequency:
                    score += query_count * self.inverse_document_frequency.get(term, 0.0) * (
                        frequency * (self.k1 + 1) / (frequency + normalizer)
                    )
            scores.append(score)
        return scores

    def rank(self, query: str, *, cutoff: int) -> list[int]:
        scores = self.scores(query)
        return sorted(range(len(scores)), key=lambda index: (-scores[index], index))[:cutoff]


def reciprocal_rank_fusion(rankings: Iterable[Iterable[str]], *, cutoff: int, constant: int = 60) -> list[str]:
    """Fuse candidate lists without treating lexical and semantic scores as comparable."""
    if constant <= 0:
        raise ValueError("RRF constant must be positive.")
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    sequence = 0
    for ranking in rankings:
        for rank, identifier in enumerate(ranking, start=1):
            if identifier not in first_seen:
                first_seen[identifier] = sequence
                sequence += 1
            scores[identifier] = scores.get(identifier, 0.0) + 1 / (constant + rank)
    return sorted(scores, key=lambda identifier: (-scores[identifier], first_seen[identifier]))[:cutoff]
