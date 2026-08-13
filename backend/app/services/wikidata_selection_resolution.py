"""Resolve user-selected title/year entries to film QIDs before any Wikipedia fetch.

Search result order alone is never trusted. A selected work must have a
Wikidata film type and a matching release year; its English Wikipedia sitelink
is then the only title sent to wikipedia-api.
"""
from __future__ import annotations

import re
import time
import unicodedata
from collections.abc import Callable
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.wikidata_raw import WIKIDATA_API, fetch_entities

FILM_QID = "Q11424"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
MIN_REQUEST_INTERVAL_SECONDS = 1.0


def normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed.casefold() if char.isalnum())


def entity_ids(claims: list[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(value, dict) and isinstance(value.get("id"), str):
            values.add(value["id"])
    return values


def release_years(claims: list[dict[str, Any]]) -> set[int]:
    years: set[int] = set()
    for claim in claims:
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(value, dict) and isinstance(value.get("time"), str):
            match = re.match(r"[+-](\d{4})-", value["time"])
            if match:
                years.add(int(match.group(1)))
    return years


def is_film_in_year(entity: dict[str, Any], year: int) -> bool:
    return FILM_QID in entity_ids(entity.get("claims", {}).get("P31", [])) and year in release_years(entity.get("claims", {}).get("P577", []))


def title_score(entity: dict[str, Any], title: str) -> int:
    expected = normalized(title)
    labels = [item.get("value", "") for item in entity.get("labels", {}).values()]
    aliases = [item.get("value", "") for values in entity.get("aliases", {}).values() for item in values]
    return 1 if expected in {normalized(value) for value in [*labels, *aliases]} else 0


def _request_search_ids(title: str, language: str) -> list[str]:
    headers = {"User-Agent": get_settings().wikidata_user_agent, "Accept-Encoding": "gzip, deflate"}
    for attempt in range(4):
        with httpx.Client(timeout=30, headers=headers) as client:
            response = client.get(WIKIDATA_API, params={
                "action": "wbsearchentities", "format": "json", "language": language,
                "type": "item", "limit": 10, "search": title,
            })
        if response.status_code in {401, 403}:
            raise RuntimeError(f"Wikidata denied title resolution ({response.status_code}); stopping.")
        if response.status_code == 429:
            time.sleep(float(response.headers.get("Retry-After", "60")))
            continue
        if response.status_code in {502, 503, 504} and attempt < 3:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        return [item["id"] for item in response.json().get("search", []) if isinstance(item.get("id"), str) and item["id"].startswith("Q")]
    raise RuntimeError("Wikidata title resolution remained unavailable after bounded retries.")


def search_ids(title: str) -> list[str]:
    """The inexpensive primary route: English Wikidata labels and aliases."""
    return _request_search_ids(title, "en")


def multilingual_search_ids(title: str) -> list[str]:
    """Fallback for original-language or transliterated titles."""
    return _request_search_ids(title, "mul")


def wikipedia_search_ids(title: str) -> list[str]:
    """Resolve alternate/original titles through English Wikipedia pageprops.

    Wikipedia search is an independent discovery route. It never publishes a
    match by itself: the caller still validates the returned Wikidata entity's
    film type and release year.
    """
    headers = {"User-Agent": get_settings().wikidata_user_agent, "Accept-Encoding": "gzip, deflate"}
    with httpx.Client(timeout=30, headers=headers) as client:
        response = client.get(WIKIPEDIA_API, params={
            "action": "query", "format": "json", "formatversion": "2",
            "list": "search", "srsearch": title, "srnamespace": 0, "srlimit": 10,
            "redirects": "1", "maxlag": "5",
        })
        if response.status_code in {401, 403}:
            raise RuntimeError(f"Wikipedia denied title resolution ({response.status_code}); stopping.")
        if response.status_code == 429:
            raise RuntimeError("Wikipedia rate-limited title resolution; stop and retry later.")
        response.raise_for_status()
        titles = [item.get("title") for item in response.json().get("query", {}).get("search", []) if item.get("title")]
        if not titles:
            return []
        response = client.get(WIKIPEDIA_API, params={
            "action": "query", "format": "json", "formatversion": "2",
            "titles": "|".join(titles), "prop": "pageprops", "ppprop": "wikibase_item",
            "redirects": "1", "maxlag": "5",
        })
        if response.status_code in {401, 403}:
            raise RuntimeError(f"Wikipedia denied page identity lookup ({response.status_code}); stopping.")
        if response.status_code == 429:
            raise RuntimeError("Wikipedia rate-limited page identity lookup; stop and retry later.")
        response.raise_for_status()
        return [
            page.get("pageprops", {}).get("wikibase_item")
            for page in response.json().get("query", {}).get("pages", [])
            if page.get("pageprops", {}).get("wikibase_item")
        ]


def multi_source_search_ids(title: str) -> list[str]:
    """Union all discovery routes; retained for direct diagnostic use.

    The bulk resolver uses the English route first and calls the other routes
    only for titles that fail film/year validation. That materially reduces
    traffic while preserving the independent-source fallback.
    """
    candidates: list[str] = []
    for searcher in (search_ids, multilingual_search_ids, wikipedia_search_ids):
        for qid in searcher(title):
            if qid not in candidates:
                candidates.append(qid)
        time.sleep(MIN_REQUEST_INTERVAL_SECONDS)
    return candidates


def resolve_entries(
    entries: list[dict[str, Any]],
    *,
    searcher: Callable[[str], list[str]] = search_ids,
    fetcher: Callable[[list[str]], dict[str, dict[str, Any]]] = fetch_entities,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve title/year selections with cheap-first, auditable fallbacks.

    Requests are serial and paced.  The primary Wikidata route handles the
    ordinary case; multilingual Wikidata and English Wikipedia are queried only
    for title/year misses.  Each accepted result still requires a film P31,
    matching release year, and an English Wikipedia sitelink.
    """
    candidate_ids: dict[int, list[str]] = {}
    all_ids: set[str] = set()
    for index, entry in enumerate(entries):
        ids = searcher(str(entry["title"]))
        candidate_ids[index] = ids
        all_ids.update(ids)
        if (index + 1) % 10 == 0 or index + 1 == len(entries):
            print(f"resolution primary search: {index + 1}/{len(entries)}", flush=True)
        if index + 1 < len(entries):
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS)
    entities = fetcher(sorted(all_ids))
    selected: dict[int, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        year = int(entry["release_year"])
        matches = [entities[qid] for qid in candidate_ids[index] if qid in entities and is_film_in_year(entities[qid], year)]
        if matches:
            selected[index] = max(matches, key=lambda entity: title_score(entity, str(entry["title"])))

    fallback_ids: dict[int, list[str]] = {}
    for ordinal, index in enumerate((index for index in range(len(entries)) if index not in selected), start=1):
        entry = entries[index]
        ids: list[str] = []
        for fallback in (multilingual_search_ids, wikipedia_search_ids):
            for qid in fallback(str(entry["title"])):
                if qid not in ids:
                    ids.append(qid)
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS)
        fallback_ids[index] = ids
        if ordinal % 5 == 0 or ordinal == len(entries) - len(selected):
            print(f"resolution fallback search: {ordinal}/{len(entries) - len(selected)}", flush=True)
        if ordinal < len(entries) - len(selected):
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS)
    fallback_entities = fetcher(sorted({qid for ids in fallback_ids.values() for qid in ids})) if fallback_ids else {}
    for index, ids in fallback_ids.items():
        entry = entries[index]
        matches = [fallback_entities[qid] for qid in ids if qid in fallback_entities and is_film_in_year(fallback_entities[qid], int(entry["release_year"]))]
        if matches:
            selected[index] = max(matches, key=lambda entity: title_score(entity, str(entry["title"])))

    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        selected_entity = selected.get(index)
        if not selected_entity:
            unresolved.append({**entry, "resolution_reason": "no film QID with matching release year after Wikidata and Wikipedia fallback"})
            continue
        enwiki = selected_entity.get("sitelinks", {}).get("enwiki", {}).get("title")
        if not enwiki:
            unresolved.append({**entry, "resolution_reason": "film QID has no English Wikipedia sitelink", "wikidata_id": selected_entity["id"]})
            continue
        resolved.append({
            **entry, "wikidata_id": selected_entity["id"], "wikipedia_title": enwiki,
            "resolution_method": "Wikidata English search or multilingual/Wikipedia fallback + direct P31 film + P577 release-year + enwiki sitelink",
        })
    return resolved, unresolved
