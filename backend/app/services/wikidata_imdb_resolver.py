"""Resolve manifest films to Wikidata QIDs through exact IMDb P345 values.

This is a discovery lead, not a canonical merge. Multiple QIDs are reported
for review; downstream raw snapshots must still verify film type and P345.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.services.imdb_dataset import IMDB_ID, ImdbDataset
from app.services.movie_data_gateway import manifest_seeds, resolve_seed


ENDPOINT = "https://query.wikidata.org/sparql"


def imdb_qid_query(imdb_ids: list[str]) -> str:
    if not imdb_ids or len(imdb_ids) > 50 or any(not IMDB_ID.fullmatch(value) for value in imdb_ids):
        raise ValueError("Wikidata discovery batch needs 1-50 valid IMDb title IDs")
    values = " ".join(f'"{value}"' for value in sorted(set(imdb_ids)))
    return ("SELECT DISTINCT ?item ?imdb WHERE { VALUES ?imdb { " + values + " } "
            "?item wdt:P345 ?imdb; wdt:P31 wd:Q11424. }")


def qids_by_imdb(payload: dict) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for row in payload.get("results", {}).get("bindings", []):
        imdb_id = row.get("imdb", {}).get("value", "")
        qid = row.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        if IMDB_ID.fullmatch(imdb_id) and qid.startswith("Q") and qid[1:].isdigit():
            found.setdefault(imdb_id, set()).add(qid)
    return {key: sorted(values) for key, values in found.items()}


def acquire(query: str, cache_dir: Path) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
    path = cache_dir / f"wdqs_imdb_{digest[:20]}.json"
    if path.exists():
        retained = json.loads(path.read_text(encoding="utf-8"))
        if retained.get("query_sha256") != digest:
            raise ValueError("Retained WDQS query hash mismatch")
        return retained["payload"]
    with httpx.Client(timeout=60, headers={
        "User-Agent": get_settings().wikidata_user_agent,
        "Accept": "application/sparql-results+json",
    }) as client:
        response = client.get(ENDPOINT, params={"query": query, "format": "json"})
    if response.status_code in {401, 403, 429}:
        raise RuntimeError(f"Wikidata query denied or limited ({response.status_code}); stop")
    response.raise_for_status()
    payload = response.json()
    path.write_text(json.dumps({"query_sha256": digest, "query": query,
                                "endpoint": ENDPOINT, "payload": payload}, ensure_ascii=False),
                    encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover film QIDs from exact local IMDb IDs")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("/imports/imdb"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    parser.add_argument("--cache-dir", type=Path, default=Path("data/selection_sources"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    dataset = ImdbDataset(args.data_dir, args.index_dir)
    original = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    seeds = manifest_seeds(args.manifest)
    resolved = []
    for seed, row in zip(seeds, original, strict=True):
        imdb_id, method = resolve_seed(dataset, seed)
        resolved.append((row, imdb_id, method))
    identifiers = sorted({imdb_id for _, imdb_id, _ in resolved if imdb_id})
    matches: dict[str, list[str]] = {}
    for start in range(0, len(identifiers), 50):
        query = imdb_qid_query(identifiers[start:start + 50])
        matches.update(qids_by_imdb(acquire(query, args.cache_dir)))
    output, results = [], []
    for row, imdb_id, method in resolved:
        entry = dict(row)
        entry["imdb_id"] = imdb_id
        candidates = matches.get(imdb_id or "", [])
        existing = row.get("wikidata_id")
        if existing and existing not in candidates:
            status = "conflicting_existing_qid"
        elif len(candidates) == 1:
            entry["wikidata_id"] = candidates[0]
            entry["identity_source_url"] = f"https://www.wikidata.org/wiki/{candidates[0]}"
            status = "qid_found"
        else:
            status = "ambiguous_qid" if candidates else (
                "no_imdb_identity" if imdb_id is None else "no_qid")
        output.append(entry)
        results.append({"title": row["title"], "imdb_id": imdb_id,
                        "identity_method": method, "qid_candidates": candidates, "status": status})
    if any(item["status"] == "conflicting_existing_qid" for item in results):
        raise ValueError("Input manifest QID conflicts with exact Wikidata P345 result; review before writing")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in output), encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    counts: dict[str, int] = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    print(json.dumps({"counts": counts, "output": str(args.output), "report": str(args.report)}))


if __name__ == "__main__":
    main()
