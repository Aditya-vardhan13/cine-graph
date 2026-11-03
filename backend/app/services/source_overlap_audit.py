"""Deterministic lexical overlap indicators, not evidence or duplicate judgments."""
import re


def token_shingles(text: str, width: int = 5) -> set[tuple[str, ...]]:
    if width < 1:
        raise ValueError("Shingle width must be positive.")
    tokens = re.findall(r"\w+", text.casefold())
    return {tuple(tokens[i:i + width]) for i in range(len(tokens) - width + 1)}


def source_coverage(candidate: str, existing: str, *, width: int = 5) -> dict:
    source = token_shingles(candidate, width)
    reference = token_shingles(existing, width)
    return {"candidate_shingles": len(source), "shared_shingles": len(source & reference),
            "candidate_coverage": len(source & reference) / len(source) if source else None}
