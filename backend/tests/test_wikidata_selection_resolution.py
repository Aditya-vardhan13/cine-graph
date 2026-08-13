import app.services.wikidata_selection_resolution as resolution
from app.services.wikidata_selection_resolution import multi_source_search_ids, resolve_entries


def _film(qid: str, label: str, year: int, enwiki: str) -> dict:
    return {
        "id": qid, "labels": {"en": {"value": label}}, "aliases": {}, "sitelinks": {"enwiki": {"title": enwiki}},
        "claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
            "P577": [{"mainsnak": {"datavalue": {"value": {"time": f"+{year}-01-01T00:00:00Z"}}}}],
        },
    }


def test_resolver_rejects_a_same_title_nonfilm_before_wikipedia_fetch() -> None:
    book = {"id": "Qbook", "labels": {"en": {"value": "Interstellar"}}, "aliases": {}, "sitelinks": {"enwiki": {"title": "Interstellar"}}, "claims": {"P31": [], "P577": []}}
    film = _film("Qfilm", "Interstellar", 2014, "Interstellar (film)")
    resolved, unresolved = resolve_entries(
        [{"position": 1, "title": "Interstellar", "release_year": 2014}],
        searcher=lambda _: ["Qbook", "Qfilm"], fetcher=lambda _: {"Qbook": book, "Qfilm": film},
    )
    assert unresolved == []
    assert resolved[0]["wikidata_id"] == "Qfilm"
    assert resolved[0]["wikipedia_title"] == "Interstellar (film)"


def test_multi_source_search_unions_independent_title_routes(monkeypatch) -> None:
    monkeypatch.setattr(resolution, "search_ids", lambda _: ["Q1", "Q2"])
    monkeypatch.setattr(resolution, "wikipedia_search_ids", lambda _: ["Q2", "Q3"])
    monkeypatch.setattr(resolution.time, "sleep", lambda _: None)
    assert multi_source_search_ids("Sen to Chihiro no kamikakushi") == ["Q1", "Q2", "Q3"]
