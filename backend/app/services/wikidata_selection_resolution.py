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

from app.services.wikidata_raw import fetch_entities

FILM_QID = "Q11424"
# These are direct Wikidata subclasses used by mainstream feature-film records.
# The resolver keeps the original P31 evidence; accepting them prevents an
# animated feature from being incorrectly discarded merely for being specific.
FILM_TYPE_QIDS = {FILM_QID, "Q202866", "Q20650540"}
class WikidataDiscoveryUnavailable(RuntimeError):
    """Raised when title discovery would require a robots-disallowed route."""


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
    return bool(FILM_TYPE_QIDS & entity_ids(entity.get("claims", {}).get("P31", []))) and year in release_years(entity.get("claims", {}).get("P577", []))


def is_film(entity: dict[str, Any]) -> bool:
    return bool(FILM_TYPE_QIDS & entity_ids(entity.get("claims", {}).get("P31", [])))


def title_score(entity: dict[str, Any], title: str) -> int:
    expected = normalized(title)
    labels = [item.get("value", "") for item in entity.get("labels", {}).values()]
    aliases = [item.get("value", "") for values in entity.get("aliases", {}).values() for item in values]
    return 1 if expected in {normalized(value) for value in [*labels, *aliases]} else 0


def search_ids(title: str) -> list[str]:
    """Refuse hidden network discovery through the blocked Action API route."""
    raise WikidataDiscoveryUnavailable(
        "Wikidata title search is disabled because /w/api.php is disallowed by current robots.txt. "
        "Resolve against local/TMDB candidates or supply a reviewed QID."
    )


def multilingual_search_ids(title: str) -> list[str]:
    """Refuse multilingual discovery through the blocked Action API route."""
    return search_ids(title)


def wikipedia_search_ids(title: str) -> list[str]:
    """Refuse API search until a robots-compliant article-page resolver exists."""
    raise WikidataDiscoveryUnavailable(
        "Wikipedia Action API title/pageprops search is disallowed by current robots.txt; "
        "resolve through an approved local/source candidate instead."
    )


def wikipedia_title_year_search_ids(title: str, year: int) -> list[str]:
    """A precise fallback for ambiguous titles such as ``Anand`` or ``Coco``."""
    return wikipedia_search_ids(f"{title} {year} film")


def multi_source_search_ids(
    title: str,
    *,
    search_routes: tuple[Callable[[str], list[str]], ...] | None = None,
    delay_seconds: float | None = None,
) -> list[str]:
    """Union all discovery routes; retained for direct diagnostic use.

    The bulk resolver uses the English route first and calls the other routes
    only for titles that fail film/year validation. That materially reduces
    traffic while preserving the independent-source fallback.
    """
    candidates: list[str] = []
    if not search_routes:
        raise WikidataDiscoveryUnavailable(
            "No title-search route is enabled; provide explicit permitted discovery callbacks."
        )
    for searcher in search_routes:
        for qid in searcher(title):
            if qid not in candidates:
                candidates.append(qid)
        wait = 1.0 if delay_seconds is None else max(0.0, delay_seconds)
        if wait > 0:
            time.sleep(wait)
    return candidates


def resolve_entries(
    entries: list[dict[str, Any]],
    *,
    searcher: Callable[[str], list[str]] | None = None,
    fetcher: Callable[[list[str]], dict[str, dict[str, Any]]] = fetch_entities,
    fallback_searchers: tuple[Callable[[str, int], list[str]], ...] = (),
    delay_seconds: float | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve title/year selections with cheap-first, auditable fallbacks.

    Discovery is supplied by the caller so this use case cannot silently call
    a route disallowed by robots.txt. Known QIDs are fetched through EntityData.
    Each accepted result still requires film type, matching release year and
    an English Wikipedia sitelink evidence.
    """
    candidate_ids: dict[int, list[str]] = {}
    all_ids: set[str] = set()
    for index, entry in enumerate(entries):
        ids = [str(entry["wikidata_id"])] if entry.get("wikidata_id") else (
            searcher(str(entry["title"])) if searcher else []
        )
        candidate_ids[index] = ids
        all_ids.update(ids)
        if (index + 1) % 10 == 0 or index + 1 == len(entries):
            print(f"resolution primary search: {index + 1}/{len(entries)}", flush=True)
        if index + 1 < len(entries):
            wait = 1.0 if delay_seconds is None else max(0.0, delay_seconds)
            if wait > 0:
                time.sleep(wait)
    entities = fetcher(sorted(all_ids)) if all_ids else {}
    selected: dict[int, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        year = int(entry["release_year"])
        # A reconciled input can deliberately preserve a source-year conflict
        # (for example, a festival date in Wikidata versus a theatrical date in
        # the enwiki infobox). Its final admission is still checked against the
        # retained Wikipedia revision by selection_audit.
        evidence_kind = entry.get("selection_year_evidence", {}).get("kind") if isinstance(entry.get("selection_year_evidence"), dict) else None
        matches = [
            entities[qid] for qid in candidate_ids[index] if qid in entities and (
                is_film_in_year(entities[qid], year)
                or (entry.get("wikidata_id") == qid and evidence_kind == "enwiki_infobox_release" and is_film(entities[qid]))
            )
        ]
        if matches:
            selected[index] = max(matches, key=lambda entity: title_score(entity, str(entry["title"])))

    fallback_ids: dict[int, list[str]] = {}
    for ordinal, index in enumerate((index for index in range(len(entries)) if index not in selected), start=1):
        entry = entries[index]
        ids: list[str] = []
        for fallback in fallback_searchers:
            for qid in fallback(str(entry["title"]), int(entry["release_year"])):
                if qid not in ids:
                    ids.append(qid)
            wait = 1.0 if delay_seconds is None else max(0.0, delay_seconds)
            if wait > 0:
                time.sleep(wait)
        fallback_ids[index] = ids
        if ordinal % 5 == 0 or ordinal == len(entries) - len(selected):
            print(f"resolution fallback search: {ordinal}/{len(entries) - len(selected)}", flush=True)
        if ordinal < len(entries) - len(selected):
            wait = 1.0 if delay_seconds is None else max(0.0, delay_seconds)
            if wait > 0:
                time.sleep(wait)
    all_fallback_ids = {qid for ids in fallback_ids.values() for qid in ids}
    fallback_entities = fetcher(sorted(all_fallback_ids)) if all_fallback_ids else {}
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
            reason = (
                "no film QID with matching release year after supplied discovery routes"
                if entry.get("wikidata_id") or searcher or fallback_searchers
                else "no Wikidata QID supplied; automatic web title search is disabled until a robots-compliant route is configured"
            )
            unresolved.append({**entry, "resolution_reason": reason})
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
