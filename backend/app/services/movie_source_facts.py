"""Source-shaped film facts. Extraction is not a claim of canonical truth."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MovieSourceFact:
    locator: str
    predicate: str
    value: dict[str, Any]
    qualifiers: dict[str, Any]
    source_property: str
    review_status: str = "resolved"


def _number(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def imdb_facts(bundle: dict[str, Any]) -> list[MovieSourceFact]:
    basics = bundle["basics"]
    facts: list[MovieSourceFact] = []

    def add(locator: str, predicate: str, value: dict[str, Any], *, status: str = "resolved") -> None:
        facts.append(MovieSourceFact(locator, predicate, value, {}, locator.split(".")[0], status))

    add("basics.tconst", "imdb_identifier", {"value": bundle["tconst"]})

    for field, predicate in (("primaryTitle", "title"), ("originalTitle", "original_title")):
        if basics.get(field) not in (None, "", "\\N"):
            add(f"basics.{field}", predicate, {"text": basics[field]})
    year = _number(basics.get("startYear", ""))
    if year:
        add("basics.startYear", "release_event", {"year": year, "precision": "year"})
    runtime = _number(basics.get("runtimeMinutes", ""))
    if runtime:
        add("basics.runtimeMinutes", "runtime", {"minutes": runtime})
    if basics.get("genres") not in (None, "", "\\N"):
        for index, genre in enumerate(basics["genres"].split(",")):
            add(f"basics.genres[{index}]", "genre", {"label": genre})
    for rating in bundle.get("ratings", []):
        try:
            score = float(rating["averageRating"])
            votes = int(rating["numVotes"])
        except (KeyError, TypeError, ValueError):
            continue
        add("ratings[0]", "audience_rating", {"score": score, "votes": votes, "scale": 10})

    names = bundle.get("names", {})
    seen_crew: set[tuple[str, str]] = set()
    role_map = {
        "actor": "cast", "actress": "cast", "self": "cast", "director": "director",
        "writer": "writer", "producer": "producer", "composer": "composer",
        "cinematographer": "cinematographer", "editor": "editor",
    }
    for index, credit in enumerate(bundle.get("principals", [])):
        nconst = credit.get("nconst", "")
        category = credit.get("category", "")
        role = role_map.get(category, "credit")
        try:
            characters = json.loads(credit.get("characters", "null"))
        except json.JSONDecodeError:
            characters = None
        value = {
            "imdb_person_id": nconst,
            "name": names.get(nconst, {}).get("primaryName") or nconst,
            "role": category,
            "job": None if credit.get("job") == "\\N" else credit.get("job"),
            "characters": characters if isinstance(characters, list) else [],
            "position": _number(credit.get("ordering", "")),
        }
        add(f"principals[{index}]", role, value)
        if role in {"director", "writer"}:
            seen_crew.add((role, nconst))
    for row in bundle.get("crew", []):
        for column, role in (("directors", "director"), ("writers", "writer")):
            for index, nconst in enumerate(row.get(column, "").split(",")):
                if not nconst or nconst == "\\N" or (role, nconst) in seen_crew:
                    continue
                add(f"crew.{column}[{index}]", role, {
                    "imdb_person_id": nconst,
                    "name": names.get(nconst, {}).get("primaryName") or nconst,
                    "role": role,
                })
                seen_crew.add((role, nconst))
    for index, alias in enumerate(bundle.get("akas", [])):
        title = alias.get("title")
        if title and title != "\\N":
            add(f"akas[{index}]", "alternate_title", {
                "text": title,
                "region": None if alias.get("region") == "\\N" else alias.get("region"),
                "language": None if alias.get("language") == "\\N" else alias.get("language"),
                "types": None if alias.get("types") == "\\N" else alias.get("types"),
            })
    return facts


def tmdb_facts(bundle: dict[str, Any]) -> list[MovieSourceFact]:
    facts: list[MovieSourceFact] = []

    def add(locator: str, predicate: str, value: dict[str, Any], *, status: str = "resolved") -> None:
        facts.append(MovieSourceFact(locator, predicate, value, {}, locator.split(".")[0], status))

    for field, predicate in (("title", "title"), ("original_title", "original_title"),
                             ("original_language", "original_language")):
        if bundle.get(field):
            key = "code" if field == "original_language" else "text"
            add(field, predicate, {key: bundle[field]})
    if bundle.get("release_date"):
        add("release_date", "release_event", {"date": bundle["release_date"], "precision": "day", "basis": "tmdb_primary"})
    if isinstance(bundle.get("runtime"), int) and bundle["runtime"] > 0:
        add("runtime", "runtime", {"minutes": bundle["runtime"]})
    for index, genre in enumerate(bundle.get("genres", [])):
        add(f"genres[{index}]", "genre", {"tmdb_id": genre.get("id"), "label": genre.get("name")})
    for index, country in enumerate(bundle.get("production_countries", [])):
        if country.get("iso_3166_1"):
            add(f"production_countries[{index}]", "production_country", {
                "code": country["iso_3166_1"], "name": country.get("name")})
    for field in ("budget", "revenue"):
        if isinstance(bundle.get(field), int) and bundle[field] > 0:
            add(field, field, {"amount_usd": bundle[field]}, status="review_required")
    for index, company in enumerate(bundle.get("production_companies", [])):
        if company.get("name"):
            add(f"production_companies[{index}]", "production_company", {
                "tmdb_id": company.get("id"), "name": company["name"]})
    for index, credit in enumerate(bundle.get("credits", {}).get("cast", [])):
        add(f"credits.cast[{index}]", "cast", {
            "tmdb_person_id": credit.get("id"), "name": credit.get("name"),
            "character": credit.get("character"), "position": credit.get("order"),
            "credit_id": credit.get("credit_id"),
        })
    crew_map = {"Director": "director", "Screenplay": "writer", "Writer": "writer",
                "Story": "writer", "Producer": "producer", "Executive Producer": "producer",
                "Director of Photography": "cinematographer", "Editor": "editor",
                "Original Music Composer": "composer"}
    for index, credit in enumerate(bundle.get("credits", {}).get("crew", [])):
        job = credit.get("job", "")
        add(f"credits.crew[{index}]", crew_map.get(job, "credit"), {
            "tmdb_person_id": credit.get("id"), "name": credit.get("name"),
            "job": job, "department": credit.get("department"),
            "credit_id": credit.get("credit_id"),
        })
    for country in bundle.get("release_dates", {}).get("results", []):
        code = country.get("iso_3166_1")
        for index, event in enumerate(country.get("release_dates", [])):
            date = str(event.get("release_date", ""))[:10]
            if len(date) == 10:
                add(f"release_dates.{code}[{index}]", "release_event", {
                    "date": date, "precision": "day", "country": code,
                    "release_type": event.get("type"), "certification": event.get("certification"),
                })
    for field, predicate in (("imdb_id", "imdb_identifier"), ("wikidata_id", "wikidata_identifier")):
        value = bundle.get("external_ids", {}).get(field)
        if value:
            add(f"external_ids.{field}", predicate, {"value": value})
    for index, keyword in enumerate(bundle.get("keywords", {}).get("keywords", [])):
        if keyword.get("name"):
            add(f"keywords[{index}]", "source_keyword", {
                "tmdb_id": keyword.get("id"), "label": keyword["name"]}, status="review_required")
    for index, title in enumerate(bundle.get("alternative_titles", {}).get("titles", [])):
        if title.get("title"):
            add(f"alternative_titles[{index}]", "alternate_title", {
                "text": title["title"], "region": title.get("iso_3166_1"), "type": title.get("type")})
    return facts
