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


def search_ids(title: str) -> list[str]:
    headers = {"User-Agent": get_settings().wikidata_user_agent, "Accept-Encoding": "gzip, deflate"}
    for attempt in range(4):
        with httpx.Client(timeout=30, headers=headers) as client:
            response = client.get(WIKIDATA_API, params={
                "action": "wbsearchentities", "format": "json", "language": "en", "type": "item", "limit": 10, "search": title,
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


def resolve_entries(
    entries: list[dict[str, Any]],
    *,
    searcher: Callable[[str], list[str]] = search_ids,
    fetcher: Callable[[list[str]], dict[str, dict[str, Any]]] = fetch_entities,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_ids: dict[int, list[str]] = {}
    all_ids: set[str] = set()
    for index, entry in enumerate(entries):
        ids = searcher(str(entry["title"]))
        candidate_ids[index] = ids
        all_ids.update(ids)
        if index + 1 < len(entries):
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS)
    entities = fetcher(sorted(all_ids))
    resolved: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        year = int(entry["release_year"])
        matches = [entities[qid] for qid in candidate_ids[index] if qid in entities and is_film_in_year(entities[qid], year)]
        if not matches:
            unresolved.append({**entry, "resolution_reason": "no film QID with matching release year"})
            continue
        selected = max(matches, key=lambda entity: title_score(entity, str(entry["title"])))
        enwiki = selected.get("sitelinks", {}).get("enwiki", {}).get("title")
        if not enwiki:
            unresolved.append({**entry, "resolution_reason": "film QID has no English Wikipedia sitelink", "wikidata_id": selected["id"]})
            continue
        resolved.append({
            **entry, "wikidata_id": selected["id"], "wikipedia_title": enwiki,
            "resolution_method": "wikidata_search + direct P31 film + P577 release-year + enwiki sitelink",
        })
    return resolved, unresolved
