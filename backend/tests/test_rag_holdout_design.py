import json
from pathlib import Path

import pytest

from app.services.rag_holdout_manifest import build_manifest


def test_holdout_questions_are_film_disjoint_from_development_and_titles_are_distinct():
    fixtures = Path(__file__).parent / "fixtures"
    holdout = json.loads((fixtures / "rag-holdout-questions-v1.json").read_text())
    development = json.loads((fixtures / "pair-relevance-50-v1.json").read_text())
    known = {title.casefold() for pair in development["pairs"] for title in pair["titles"]}
    identities = [(film["title"].casefold(), film["year"]) for pair in holdout["pairs"] for film in pair["films"]]
    assert len(identities) == len(set(identities)) == 8
    assert not known.intersection(title for title, _year in identities)
    assert len({p["id"] for p in holdout["pairs"]}) == 4
    assert all(len(p["questions"]) == len(set(p["questions"])) == 5 for p in holdout["pairs"])
    assert holdout["status"] == "frozen-question-design-not-yet-source-labelled"


def test_identity_mapping_preserves_frozen_questions_and_rejects_missing_films():
    fixtures = Path(__file__).parent / "fixtures"
    design = json.loads((fixtures / "rag-holdout-questions-v1.json").read_text())
    identities = json.loads((fixtures / "rag-holdout-identities-v1.json").read_text())
    manifest = build_manifest(design, identities, collection="retained")
    assert manifest["pairs"][0]["films"] == ["Q15648198", "Q180214"]
    assert manifest["pairs"][0]["questions"] == design["pairs"][0]["questions"]
    identities["films"].pop()
    with pytest.raises(ValueError, match="explicit frozen identity"):
        build_manifest(design, identities, collection="retained")
