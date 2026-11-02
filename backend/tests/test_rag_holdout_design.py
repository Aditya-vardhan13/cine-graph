import json
from pathlib import Path


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
