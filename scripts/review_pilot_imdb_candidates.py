"""Find local IMDb title candidates for unresolved pilot rows; never merge them."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.services.imdb_dataset import ImdbDataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("readiness", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("imdb_data"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = Path.cwd().resolve()
    evaluation = (project / "data/evaluation").resolve()
    if any(not p.resolve().is_relative_to(evaluation) for p in (args.pilot, args.readiness, args.output)):
        raise ValueError("Pilot, readiness and output must stay in local evaluation storage")
    if args.output.exists():
        raise FileExistsError(args.output)
    pilot_bytes = args.pilot.read_bytes()
    readiness_bytes = args.readiness.read_bytes()
    pilot = json.loads(pilot_bytes)
    films = json.loads(readiness_bytes)["films"]
    dataset = ImdbDataset(args.data_dir, args.index_dir)
    results = []
    for item in pilot["films"]:
        if item["match_status"] == "exact_title_year":
            continue
        hits = dataset.search_title(item["input_title"], item.get("input_year"), limit=8)
        catalog_by_imdb = {}
        for candidate in hits:
            for film in films:
                if candidate["tconst"] in film.get("resolved_imdb_ids", []):
                    catalog_by_imdb.setdefault(candidate["tconst"], []).append(film)
        results.append({
            "selection_rank": item["selection_rank"], "input_title": item["input_title"],
            "input_year": item["input_year"], "status": "review_required",
            "imdb_candidates": [{"tconst": hit["tconst"], "title": hit["title"],
                "year": hit["year"], "score": hit.get("score"),
                "title_year_match": hit["year"] == item["input_year"],
                "catalog_identity_candidates": [{"film_id": f["film_id"], "title": f["title"],
                    "wikidata_id": f["wikidata_id"]} for f in catalog_by_imdb.get(hit["tconst"], [])]}
                for hit in hits],
        })
    output = {"version": "pilot-imdb-identity-review-v1", "read_only": True,
              "pilot_sha256": hashlib.sha256(pilot_bytes).hexdigest(),
              "readiness_sha256": hashlib.sha256(readiness_bytes).hexdigest(),
              "unresolved_films": len(results), "candidates": results,
              "caution": "IMDb title-index candidates are discovery leads, not identity resolution or permission to publish IMDb data."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({"unresolved_films": len(results),
                      "with_imdb_candidates": sum(bool(r["imdb_candidates"]) for r in results),
                      "candidate_catalog_id_matches": sum(any(c["catalog_identity_candidates"]
                          for c in r["imdb_candidates"]) for r in results),
                      "output": str(args.output)}))


if __name__ == "__main__":
    main()
