import app.services.wikidata_selection_resolution as resolution
from app.services.wikidata_selection_resolution import multi_source_search_ids, resolve_entries


def _film(qid: str, label: str, year: int, enwiki: str, film_type: str = "Q11424") -> dict:
    return {
        "id": qid, "labels": {"en": {"value": label}}, "aliases": {}, "sitelinks": {"enwiki": {"title": enwiki}},
        "claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"id": film_type}}}}],
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
    monkeypatch.setattr(resolution, "multilingual_search_ids", lambda _: ["Q2", "Q3"])
    monkeypatch.setattr(resolution, "wikipedia_search_ids", lambda _: ["Q3", "Q4"])
    monkeypatch.setattr(resolution.time, "sleep", lambda _: None)
    assert multi_source_search_ids("Sen to Chihiro no kamikakushi") == ["Q1", "Q2", "Q3", "Q4"]


def test_resolver_uses_multilingual_and_wikipedia_routes_only_for_primary_misses(monkeypatch) -> None:
    first = _film("Qfirst", "Interstellar", 2014, "Interstellar (film)")
    fallback = _film("Qfallback", "Spirited Away", 2001, "Spirited Away")
    monkeypatch.setattr(resolution, "search_ids", lambda title: ["Qfirst"] if title == "Interstellar" else [])
    monkeypatch.setattr(resolution, "multilingual_search_ids", lambda title: ["Qfallback"] if title == "Sen to Chihiro no kamikakushi" else [])
    monkeypatch.setattr(resolution, "wikipedia_search_ids", lambda _: [])
    monkeypatch.setattr(resolution.time, "sleep", lambda _: None)
    resolved, unresolved = resolve_entries(
        [
            {"position": 1, "title": "Interstellar", "release_year": 2014},
            {"position": 2, "title": "Sen to Chihiro no kamikakushi", "release_year": 2001},
        ],
        searcher=resolution.search_ids,
        fetcher=lambda _: {"Qfirst": first, "Qfallback": fallback},
    )
    assert unresolved == []
    assert [entry["wikidata_id"] for entry in resolved] == ["Qfirst", "Qfallback"]


def test_resolver_accepts_specific_animated_feature_type() -> None:
    animated = _film("Qanimated", "Spirited Away", 2001, "Spirited Away", film_type="Q20650540")
    resolved, unresolved = resolve_entries(
        [{"position": 1, "title": "Sen to Chihiro no kamikakushi", "release_year": 2001}],
        searcher=lambda _: ["Qanimated"], fetcher=lambda _: {"Qanimated": animated},
    )
    assert unresolved == []
    assert resolved[0]["wikidata_id"] == "Qanimated"
