"""Build a reproducible Indian feature-film research manifest from CC0 IDs.

This is a *candidate selector*, not an authoritative greatest-films ranking.
It uses Wikidata's India + original-language + IMDb-ID statements to nominate
films, then the supplied local IMDb dump to verify type/year and rank available
audience signals. Every candidate and selection decision is retained locally.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.imdb_dataset import IMDB_ID, ImdbDataset


ENDPOINT = "https://query.wikidata.org/sparql"
SELECTION_VERSION = "indian-cross-language-imdb-wikidata-v2"
QID = re.compile(r"Q\d+\Z")
LANGUAGES = {
    "hi": ("Q1568", 120), "te": ("Q8097", 80),
    "ta": ("Q5885", 80), "ml": ("Q36236", 70),
    "kn": ("Q33673", 50), "bn": ("Q9610", 50),
    "mr": ("Q1571", 50),
}


@dataclass(frozen=True)
class Candidate:
    imdb_id: str
    wikidata_id: str
    language_code: str
    title: str
    year: int
    rating: float
    votes: int
    weighted_score: float


def sparql_query(language_qid: str, limit: int) -> str:
    if not QID.fullmatch(language_qid) or not 1 <= limit <= 5000:
        raise ValueError("Unsafe WDQS query parameters")
    return ("SELECT DISTINCT ?item ?imdb WHERE { "
            "?item wdt:P31 wd:Q11424; wdt:P495 wd:Q668; "
            f"wdt:P364 wd:{language_qid}; wdt:P345 ?imdb. "
            f"}} LIMIT {limit}")


def acquire_candidates(language_code: str, cache_dir: Path, *, limit: int = 2000) -> dict[str, Any]:
    qid = LANGUAGES[language_code][0]
    query = sparql_query(qid, limit)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"wdqs_{language_code}_{limit}.json"
    if cache_path.exists():
        retained = json.loads(cache_path.read_text(encoding="utf-8"))
        if retained.get("query") != query:
            raise ValueError(f"Cached query changed: {cache_path}")
        return retained
    headers = {"User-Agent": get_settings().wikidata_user_agent,
               "Accept": "application/sparql-results+json"}
    with httpx.Client(timeout=60, headers=headers) as client:
        response = client.get(ENDPOINT, params={"query": query, "format": "json"})
    if response.status_code in {401, 403, 429}:
        raise RuntimeError(f"WDQS denied or rate-limited the request ({response.status_code}); stop")
    response.raise_for_status()
    payload = response.json()
    retained = {
        "selection_version": SELECTION_VERSION,
        "endpoint": ENDPOINT,
        "query": query,
        "payload_sha256": hashlib.sha256(response.content).hexdigest(),
        "payload": payload,
    }
    cache_path.write_text(json.dumps(retained, ensure_ascii=False), encoding="utf-8")
    return retained


def parse_candidates(raw: dict[str, Any], language_code: str,
                     dataset: ImdbDataset) -> tuple[list[Candidate], dict[str, int]]:
    records: list[Candidate] = []
    rejected: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for binding in raw.get("payload", {}).get("results", {}).get("bindings", []):
        qid = binding.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        tconst = binding.get("imdb", {}).get("value", "")
        if not QID.fullmatch(qid) or not IMDB_ID.fullmatch(tconst) or (qid, tconst) in seen:
            rejected["invalid_or_duplicate_id"] = rejected.get("invalid_or_duplicate_id", 0) + 1
            continue
        seen.add((qid, tconst))
        basic = dataset.rows("basics", tconst)
        if len(basic) != 1 or basic[0].get("titleType") != "movie" or basic[0].get("isAdult") != "0":
            rejected["not_single_nonadult_movie"] = rejected.get("not_single_nonadult_movie", 0) + 1
            continue
        year_raw = basic[0].get("startYear", "")
        if not year_raw.isdigit() or not 1900 <= int(year_raw) <= 2025:
            rejected["year_outside_scope"] = rejected.get("year_outside_scope", 0) + 1
            continue
        rating = dataset.rows("ratings", tconst)
        if len(rating) != 1:
            rejected["no_rating"] = rejected.get("no_rating", 0) + 1
            continue
        try:
            votes = int(rating[0]["numVotes"])
            score = float(rating[0]["averageRating"])
        except (KeyError, ValueError):
            rejected["invalid_rating"] = rejected.get("invalid_rating", 0) + 1
            continue
        if votes < 200:
            rejected["few_votes"] = rejected.get("few_votes", 0) + 1
            continue
        # Bayesian vote shrinkage prevents a handful of ratings from outranking
        # well-observed films. This is a selection signal, not an artistic verdict.
        weighted = (votes * score + 1500 * 6.5) / (votes + 1500)
        records.append(Candidate(tconst, qid, language_code,
                                 basic[0]["primaryTitle"], int(year_raw),
                                 score, votes, round(weighted, 5)))
    records.sort(key=lambda row: (-row.weighted_score, -math.log1p(row.votes),
                                  row.year, row.imdb_id))
    return records, rejected


def ambiguous_imdb_qids(by_language: dict[str, list[Candidate]]) -> dict[str, list[str]]:
    qids: dict[str, set[str]] = {}
    for candidates in by_language.values():
        for candidate in candidates:
            qids.setdefault(candidate.imdb_id, set()).add(candidate.wikidata_id)
    return {imdb_id: sorted(values) for imdb_id, values in qids.items() if len(values) > 1}


def select_manifest(by_language: dict[str, list[Candidate]],
                    *, reviewed_ambiguous: dict[str, str] | None = None) -> tuple[list[Candidate], dict[str, int]]:
    selected: list[Candidate] = []
    counts: dict[str, int] = {code: 0 for code in LANGUAGES}
    used_ids: set[str] = set()
    ambiguous = ambiguous_imdb_qids(by_language)
    reviewed_ambiguous = reviewed_ambiguous or {}
    for code, (_, quota) in LANGUAGES.items():
        for candidate in by_language[code]:
            if counts[code] >= quota:
                break
            if candidate.imdb_id in used_ids:
                continue
            if candidate.imdb_id in ambiguous and reviewed_ambiguous.get(candidate.imdb_id) != candidate.wikidata_id:
                continue
            selected.append(candidate)
            counts[code] += 1
            used_ids.add(candidate.imdb_id)
    if len(selected) != sum(quota for _, quota in LANGUAGES.values()):
        raise ValueError(f"Quotas not met; only {len(selected)} independently identified films")
    return selected, counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Select 500 attributable Indian film research candidates")
    parser.add_argument("--data-dir", type=Path, default=Path("/imports/imdb"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/selection_sources"))
    parser.add_argument("--limit-per-language", type=int, default=2000)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--reviewed-identity-overrides", type=Path,
                        help="JSONL IMDb/QID pairs reviewed where Wikidata has duplicate IMDb IDs")
    args = parser.parse_args()
    reviewed: dict[str, str] = {}
    if args.reviewed_identity_overrides:
        for line in args.reviewed_identity_overrides.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            imdb_id, qid = row.get("imdb_id"), row.get("wikidata_id")
            if not isinstance(imdb_id, str) or not IMDB_ID.fullmatch(imdb_id) or not QID.fullmatch(str(qid)):
                raise ValueError("Reviewed override needs valid IMDb and Wikidata IDs")
            if not row.get("review_reason") or not row.get("source_url") or imdb_id in reviewed:
                raise ValueError("Reviewed override needs reason, source URL, and a unique IMDb ID")
            reviewed[imdb_id] = qid
    dataset = ImdbDataset(args.data_dir, args.index_dir)
    by_language: dict[str, list[Candidate]] = {}
    report: dict[str, Any] = {"version": SELECTION_VERSION, "source": ENDPOINT,
                              "languages": {}, "scope": "candidate research pilot, not a greatest-films verdict"}
    for index, code in enumerate(LANGUAGES):
        if index:
            time.sleep(2)  # A deliberate, single-threaded WDQS request pace.
        raw = acquire_candidates(code, args.cache_dir, limit=args.limit_per_language)
        candidates, rejected = parse_candidates(raw, code, dataset)
        by_language[code] = candidates
        report["languages"][code] = {
            "retrieved": len(raw["payload"]["results"]["bindings"]),
            "eligible": len(candidates), "rejected": rejected,
            "query_sha256": hashlib.sha256(raw["query"].encode()).hexdigest(),
            "payload_sha256": raw["payload_sha256"],
        }
    ambiguous = ambiguous_imdb_qids(by_language)
    for imdb_id, qid in reviewed.items():
        if qid not in ambiguous.get(imdb_id, []):
            raise ValueError(f"Reviewed override does not resolve a retained ambiguity: {imdb_id}")
    selected, counts = select_manifest(by_language, reviewed_ambiguous=reviewed)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text("".join(json.dumps({
        "title": row.title, "year": row.year, "imdb_id": row.imdb_id,
        "wikidata_id": row.wikidata_id, "language_code": row.language_code,
        "selection_source_url": f"https://www.wikidata.org/wiki/{row.wikidata_id}",
        "selection_signals": {
            "method": SELECTION_VERSION, "imdb_rating": row.rating,
            "imdb_votes": row.votes, "weighted_score": row.weighted_score,
            "wikidata_country": "Q668", "wikidata_language_bucket": LANGUAGES[row.language_code][0],
            "language_bucket_is_exclusive": False,
        },
    }, ensure_ascii=False) + "\n" for row in selected), encoding="utf-8")
    report["selected"] = len(selected)
    report["selected_by_language"] = counts
    report["ambiguous_imdb_qids"] = ambiguous
    report["reviewed_ambiguous"] = reviewed
    report["selection_signals"] = [row.__dict__ for row in selected]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"selected": len(selected), "by_language": counts,
                      "manifest": str(args.manifest), "report": str(args.report)}))


if __name__ == "__main__":
    main()
