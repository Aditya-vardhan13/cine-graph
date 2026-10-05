"""Read the operator-supplied IMDb TSVs without copying the full dumps into PostgreSQL.

The sparse byte-offset indexes and title lookup are local, disposable derivatives.
IMDb's public datasets are non-commercial: callers must preserve that restriction.
"""
from __future__ import annotations

import argparse
import bisect
import csv
from difflib import SequenceMatcher
import hashlib
import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


INDEX_VERSION = 1
STRIDE = 4096
FILES = {
    "basics": ("title.basics.tsv", "tconst"),
    "akas": ("title.akas.tsv", "titleId"),
    "crew": ("title.crew.tsv", "tconst"),
    "principals": ("title.principals.tsv", "tconst"),
    "ratings": ("title.ratings.tsv", "tconst"),
    "names": ("name.basics.tsv", "nconst"),
}
IMDB_ID = re.compile(r"tt\d{7,10}\Z")


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", value, flags=re.UNICODE))


def _row(header: list[str], line: bytes) -> dict[str, str]:
    values = next(csv.reader([line.decode("utf-8", errors="replace")], delimiter="\t"))
    return dict(zip(header, values, strict=False))


def _source_path(data_dir: Path, kind: str) -> Path:
    filename, _ = FILES[kind]
    return data_dir.parent / filename if kind == "names" else data_dir / filename


def build_index(data_dir: Path, index_dir: Path, *, kinds: tuple[str, ...] | None = None) -> dict[str, Any]:
    """Build sorted-file seek points plus a compact title/year search database."""
    index_dir.mkdir(parents=True, exist_ok=True)
    chosen = kinds or tuple(FILES)
    stats: dict[str, Any] = {}
    for kind in chosen:
        path = _source_path(data_dir, kind)
        filename, key_column = FILES[kind]
        if not path.is_file():
            raise FileNotFoundError(path)
        title_db = None
        if kind == "basics":
            title_path = index_dir / "titles.sqlite.next"
            if title_path.exists():
                title_path.unlink()
            title_db = sqlite3.connect(title_path)
            title_db.execute("CREATE TABLE titles (tconst TEXT NOT NULL, title TEXT NOT NULL, normalized_title TEXT NOT NULL, year INTEGER, original_language TEXT)")
        offsets: list[list[str | int]] = []
        count = 0
        included = 0
        digest = hashlib.sha256()
        previous_key = ""
        with path.open("rb") as stream:
            header_line = stream.readline()
            digest.update(header_line)
            header = header_line.decode("utf-8-sig").rstrip("\r\n").split("\t")
            if key_column not in header:
                raise ValueError(f"{filename} has no {key_column} column")
            key_position = header.index(key_column)
            while True:
                offset = stream.tell()
                line = stream.readline()
                if not line:
                    break
                digest.update(line)
                values = line.rstrip(b"\r\n").split(b"\t")
                if len(values) <= key_position:
                    raise ValueError(f"Malformed row at byte {offset} in {filename}")
                key = values[key_position].decode("ascii")
                if previous_key and key < previous_key:
                    raise ValueError(f"{filename} is not sorted by {key_column} at byte {offset}")
                previous_key = key
                if count % STRIDE == 0:
                    offsets.append([key, offset])
                count += 1
                if title_db is not None:
                    record = dict(zip(header, (value.decode("utf-8", errors="replace") for value in values), strict=False))
                    if record.get("titleType") in {"movie", "tvMovie"}:
                        year = record.get("startYear", "")
                        year_value = int(year) if year.isdigit() else None
                        for title in {record.get("primaryTitle", ""), record.get("originalTitle", "")}:
                            if title and title != "\\N":
                                title_db.execute(
                                    "INSERT INTO titles VALUES (?, ?, ?, ?, NULL)",
                                    (key, title, normalize_title(title), year_value),
                                )
                        included += 1
                    if count % 20000 == 0:
                        title_db.commit()
        if title_db is not None:
            title_db.execute("CREATE INDEX titles_name_year ON titles(normalized_title, year)")
            title_db.execute("CREATE INDEX titles_id ON titles(tconst)")
            title_db.execute("CREATE INDEX titles_year ON titles(year)")
            title_db.commit()
            title_db.close()
            title_path.replace(index_dir / "titles.sqlite")
        stat = path.stat()
        metadata = {
            "index_version": INDEX_VERSION, "filename": filename, "key_column": key_column,
            "size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "sha256": digest.hexdigest(),
            "rows": count, "stride": STRIDE, "offsets": offsets,
        }
        target = index_dir / f"{kind}.sparse.json"
        pending = index_dir / f"{kind}.sparse.json.next"
        pending.write_text(json.dumps(metadata, separators=(",", ":")), encoding="utf-8")
        pending.replace(target)
        stats[kind] = {"rows": count, "seek_points": len(offsets), "movie_titles": included}
    return stats


class ImdbDataset:
    def __init__(self, data_dir: Path, index_dir: Path):
        self.data_dir = data_dir
        self.index_dir = index_dir
        self._indexes: dict[str, dict[str, Any]] = {}
        self._index_keys: dict[str, list[str]] = {}

    def _index(self, kind: str) -> dict[str, Any]:
        if kind not in self._indexes:
            path = _source_path(self.data_dir, kind)
            metadata = json.loads((self.index_dir / f"{kind}.sparse.json").read_text(encoding="utf-8"))
            stat = path.stat()
            if (metadata.get("index_version") != INDEX_VERSION or metadata.get("size") != stat.st_size
                    or metadata.get("mtime_ns") != stat.st_mtime_ns):
                raise ValueError(f"IMDb {kind} index is stale; rebuild it before querying")
            self._indexes[kind] = metadata
            self._index_keys[kind] = [point[0] for point in metadata["offsets"]]
        return self._indexes[kind]

    def rows(self, kind: str, key: str) -> list[dict[str, str]]:
        metadata = self._index(kind)
        points = metadata["offsets"]
        if not points:
            return []
        keys = self._index_keys[kind]
        block = bisect.bisect_right(keys, key) - 1
        if block < 0:
            return []
        # An ID can span arbitrarily many sampled blocks (for example, many
        # localized titles). Start before the *first* matching seek point.
        first_matching_block = bisect.bisect_left(keys, key)
        start_block = (max(0, first_matching_block - 1)
                       if first_matching_block < len(keys) and keys[first_matching_block] == key
                       else block)
        start = points[max(0, start_block)][1]
        path = _source_path(self.data_dir, kind)
        with path.open("rb") as stream:
            header = stream.readline().decode("utf-8-sig").rstrip("\r\n").split("\t")
            stream.seek(start)
            results = []
            while line := stream.readline():
                record = _row(header, line)
                value = record[metadata["key_column"]]
                if value > key:
                    break
                if value == key:
                    results.append(record)
            return results

    def search_title(self, title: str, year: int | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
        normalized = normalize_title(title)
        if not normalized:
            return []
        with sqlite3.connect(self.index_dir / "titles.sqlite") as db:
            db.row_factory = sqlite3.Row
            if year is None:
                rows = db.execute(
                    "SELECT DISTINCT tconst,title,year FROM titles WHERE normalized_title=? ORDER BY year DESC LIMIT ?",
                    (normalized, limit),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT DISTINCT tconst,title,year FROM titles WHERE normalized_title=? AND year BETWEEN ? AND ? ORDER BY ABS(year-?),tconst LIMIT ?",
                    (normalized, year - 1, year + 1, year, limit),
                ).fetchall()
            exact = [dict(row, score=1.0) for row in rows]
            if exact or year is None:
                return exact
            # Alternate punctuation, subtitles and translations often defeat an
            # exact title match. Restrict fuzzy discovery to the release-year
            # window; a scorer only proposes identities, never publishes one.
            candidates = db.execute(
                "SELECT DISTINCT tconst,title,normalized_title,year FROM titles WHERE year BETWEEN ? AND ?",
                (year - 1, year + 1),
            ).fetchall()
            query_tokens = set(normalized.split())
            ranked = []
            for row in candidates:
                candidate = row["normalized_title"]
                candidate_tokens = set(candidate.split())
                if not query_tokens or not candidate_tokens or not query_tokens & candidate_tokens:
                    continue
                overlap = len(query_tokens & candidate_tokens) / len(query_tokens | candidate_tokens)
                containment = len(query_tokens & candidate_tokens) / len(query_tokens)
                ratio = SequenceMatcher(None, normalized, candidate).ratio()
                score = max(ratio, 0.85 * containment + 0.15 * overlap)
                if score >= 0.62:
                    ranked.append(dict(row, score=round(score, 4)))
            ranked.sort(key=lambda row: (-row["score"], abs(row["year"] - year), row["tconst"]))
            return ranked[:limit]

    def film_bundle(self, tconst: str) -> dict[str, Any]:
        if not IMDB_ID.fullmatch(tconst):
            raise ValueError("Expected an IMDb title identifier")
        basics = self.rows("basics", tconst)
        if len(basics) != 1 or basics[0]["titleType"] not in {"movie", "tvMovie"}:
            raise ValueError(f"IMDb {tconst} is not a single movie record")
        principals = self.rows("principals", tconst)
        crew = self.rows("crew", tconst)
        person_ids = {row["nconst"] for row in principals}
        for row in crew:
            for field in ("directors", "writers"):
                person_ids.update(value for value in row[field].split(",") if value != "\\N")
        names = {person_id: rows[0] for person_id in sorted(person_ids)
                 if (rows := self.rows("names", person_id))}
        return {
            "dataset_sha256": {kind: self._index(kind)["sha256"] for kind in FILES},
            "tconst": tconst,
            "basics": basics[0],
            "ratings": self.rows("ratings", tconst),
            "crew": crew,
            "principals": principals,
            "akas": self.rows("akas", tconst),
            "names": names,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build disposable local IMDb TSV seek indexes")
    parser.add_argument("--data-dir", type=Path, default=Path("/imports/imdb"))
    parser.add_argument("--index-dir", type=Path, default=Path("data/imdb_index"))
    args = parser.parse_args()
    print(json.dumps(build_index(args.data_dir, args.index_dir), indent=2))


if __name__ == "__main__":
    main()
