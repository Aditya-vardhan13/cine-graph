"""Freeze a ranked title-list pilot against the read-only catalog audit."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("--imdb-review", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evaluation = Path("data/evaluation").resolve()
    project = Path.cwd().resolve()
    if args.csv.resolve() != (project / "imdb_top_1000.csv").resolve():
        raise ValueError("Candidate list must be the supplied project imdb_top_1000.csv")
    scoped = [args.readiness, args.output] + ([args.imdb_review] if args.imdb_review else [])
    if any(not path.resolve().is_relative_to(evaluation) for path in scoped):
        raise ValueError("Readiness input and pilot output must stay in local data/evaluation")
    if args.output.exists():
        raise FileExistsError(args.output)
    csv_bytes = args.csv.read_bytes()
    csv_rows = list(csv.DictReader(csv_bytes.decode("utf-8-sig").splitlines()))
    if len(csv_rows) < 100:
        raise ValueError("Candidate list has fewer than 100 records")
    films = json.loads(args.readiness.read_text(encoding="utf-8"))["films"]
    imdb_review = json.loads(args.imdb_review.read_text(encoding="utf-8"))["candidates"] if args.imdb_review else []
    review_by_rank = {row["selection_rank"]: row for row in imdb_review}
    by_key: dict[tuple[str, int | None], list[dict]] = {}
    by_alias_key: dict[tuple[str, int | None], list[dict]] = {}
    for film in films:
        years = {int(year) for year in film.get("release_years_from_resolved_events", [])}
        if film.get("release_date"):
            years.add(int(film["release_date"][:4]))
        for year in years:
            by_key.setdefault((normalize_title(film["title"]), year), []).append(film)
            for alias in film.get("aliases", []):
                by_alias_key.setdefault((normalize_title(alias["value"]), year), []).append(
                    {**film, "matched_alias": alias})
    pilot = []
    for rank, row in enumerate(csv_rows[:100], start=1):
        title = (row.get("Series_Title") or "").strip()
        try:
            year = int(row["Released_Year"])
        except (TypeError, ValueError):
            year = None
        candidates = by_key.get((normalize_title(title), year), []) if year else []
        match_type = "canonical_title"
        if not candidates and year:
            candidates = by_alias_key.get((normalize_title(title), year), [])
            match_type = "catalog_alias"
        status = ("exact_title_year" if match_type == "canonical_title" else "exact_alias_year") if len(candidates) == 1 else (
            "ambiguous_exact_title_year" if len(candidates) > 1 else "review_required_no_exact_title_year")
        crosslink = review_by_rank.get(rank)
        imdb_links = []
        if not candidates and crosslink:
            imdb_links = [candidate for candidate in crosslink["imdb_candidates"]
                          if candidate["title_year_match"] and len(candidate["catalog_identity_candidates"]) == 1]
            if len(imdb_links) == 1:
                status = "review_required_unique_imdb_crosslink"
        pilot.append({"selection_rank": rank, "input_title": title, "input_year": year,
                      "input_source": "imdb_top_1000.csv", "input_imdb_rating": row.get("IMDB_Rating"),
                      "match_status": status,
                      "catalog_candidates": [{"film_id": c["film_id"], "title": c["title"],
                          "release_date": c["release_date"], "wikidata_id": c["wikidata_id"],
                          "release_years_from_resolved_events": c["release_years_from_resolved_events"],
                          "language": c["language"], "matched_alias": c.get("matched_alias"),
                          "gaps": c["gaps"]} for c in candidates] + [
                          {"film_id": item["film_id"], "title": item["title"],
                           "wikidata_id": item["wikidata_id"], "imdb_id": link["tconst"],
                           "identity_evidence": "IMDb title/year candidate shares tconst with resolved catalog IMDb identifier",
                           "review_required": True}
                          for link in imdb_links for item in link["catalog_identity_candidates"]]})
    payload = {"version": "catalog-pilot-top100-v1", "selection": "first 100 input rows in supplied CSV order",
               "candidate_csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
               "readiness_report_sha256": hashlib.sha256(args.readiness.read_bytes()).hexdigest(),
               "imdb_review_sha256": hashlib.sha256(args.imdb_review.read_bytes()).hexdigest() if args.imdb_review else None,
               "film_count": len(pilot), "match_counts": {
                   status: sum(item["match_status"] == status for item in pilot)
                   for status in sorted({item["match_status"] for item in pilot})},
               "films": pilot,
               "caution": "The input file is not certified as a current IMDb ranking. Exact title/year is a candidate match, not independently verified identity."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"films": len(pilot), "match_counts": payload["match_counts"],
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
