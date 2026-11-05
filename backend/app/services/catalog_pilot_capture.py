"""Local, checkpointed source capture for a frozen catalog pilot selection.

This is an acquisition artifact only: it writes exact source snapshots and an
audit manifest under an ignored local output directory. It does not mutate the
operational catalog or publish assertions/passages.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from app.core.config import get_settings
from app.services.wikidata_raw import (
    WikidataEntityDataFetcher,
    entity_from_entitydata,
)
from app.services.wikidata_selection_resolution import entity_ids, is_film, is_film_in_year, release_years, title_score
from app.services.wikipedia_article_capture import WikipediaArticleFetcher
from app.services.wikipedia_article_html import PARSER_VERSION, article_url, parse_article_html


class CatalogPilotCaptureError(RuntimeError):
    """The selection or immutable local capture state failed validation."""


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _atomic_write(path: Path, payload: bytes) -> None:
    if path.exists():
        if path.read_bytes() != payload:
            raise CatalogPilotCaptureError(f"Refusing to overwrite immutable capture: {path}")
        return
    _atomic_replace(path, payload)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_replace(path, (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def _load_selection(path: Path, limit: int) -> tuple[list[dict[str, Any]], str]:
    if limit < 1:
        raise CatalogPilotCaptureError("Pilot limit must be a positive integer.")
    raw = path.read_bytes()
    document = json.loads(raw)
    films = document.get("films")
    if not isinstance(films, list) or len(films) < limit:
        raise CatalogPilotCaptureError("Selection manifest does not contain the requested number of films.")
    selected: list[dict[str, Any]] = []
    seen_qids: set[str] = set()
    for rank, film in enumerate(films[:limit], start=1):
        title = str(film.get("input_title") or "").strip()
        year = film.get("input_year")
        candidates = film.get("catalog_candidates") or []
        qids = sorted({str(item.get("wikidata_id")) for item in candidates if item.get("wikidata_id")})
        if film.get("match_status") != "exact_title_year" or len(qids) != 1:
            raise CatalogPilotCaptureError(
                f"Selection row {rank} is not an unambiguous exact-title/year candidate; review it first."
            )
        qid = qids[0]
        if not title or not isinstance(year, int) or qid in seen_qids:
            raise CatalogPilotCaptureError(f"Selection row {rank} has incomplete or duplicate identity input.")
        seen_qids.add(qid)
        selected.append({"selection_rank": rank, "title": title, "year": year, "qid": qid})
    return selected, sha256(raw).hexdigest()


def _write_checkpoint(path: Path, manifest: dict[str, Any]) -> None:
    manifest["counts"] = {
        "requested": len(manifest["films"]),
        "identity_verified": sum(film.get("identity_status") == "verified" for film in manifest["films"]),
        "wikipedia_captured": sum(film.get("wikipedia_status") == "captured" for film in manifest["films"]),
        "failed": sum(film.get("capture_status") == "failed" for film in manifest["films"]),
        "identity_review_required": sum(film.get("identity_status") == "review_required" for film in manifest["films"]),
    }
    manifest["run_status"] = "complete" if all(
        film.get("identity_status") == "verified" and film.get("wikipedia_status") == "captured"
        for film in manifest["films"]
    ) else "in_progress"
    _atomic_write_json(path, manifest)


def _read_or_create_manifest(path: Path, selection: list[dict[str, Any]], selection_hash: str) -> dict[str, Any]:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("selection_sha256") != selection_hash:
            raise CatalogPilotCaptureError("Existing checkpoint belongs to a different frozen selection.")
        if existing.get("films") and [
            (item.get("title"), item.get("year"), item.get("qid")) for item in existing["films"]
        ] != [(item["title"], item["year"], item["qid"]) for item in selection]:
            raise CatalogPilotCaptureError("Existing checkpoint film identities do not match the selection.")
        return existing
    manifest = {
        "schema": "cinegraph.catalog-pilot-capture/v1",
        "selection_sha256": selection_hash,
        "capture_policy": {
            "wikidata_route": "known-QID Special:EntityData JSON only",
            "wikipedia_route": "known enwiki sitelink ordinary /wiki/ page only",
            "robots_required": True,
            "minimum_interval_seconds": 1.0,
            "concurrency": 1,
            "stop_on_denial_or_rate_limit": True,
        },
        "films": [
            {**item, "capture_status": "pending", "identity_status": "pending", "wikipedia_status": "pending"}
            for item in selection
        ],
    }
    _write_checkpoint(path, manifest)
    return manifest


def _source_file(output_dir: Path, source: str, qid: str, payload: bytes, suffix: str) -> tuple[str, str]:
    digest = sha256(payload).hexdigest()
    path = output_dir / "snapshots" / source / qid / f"{digest}{suffix}"
    _atomic_write(path, payload)
    return path.relative_to(output_dir).as_posix(), digest


def capture_catalog_pilot(selection_path: Path, output_dir: Path, *, limit: int = 10) -> dict[str, Any]:
    """Capture and identity-check a small frozen selection, checkpointing each work.

    Any network failure stops the run. Rerunning the same command is an
    explicit resume; completed, hash-verified captures are reused.
    """
    selection, selection_hash = _load_selection(selection_path, limit)
    output_dir = output_dir.resolve()
    manifest_path = output_dir / "capture-manifest.json"
    manifest = _read_or_create_manifest(manifest_path, selection, selection_hash)
    settings = get_settings()
    interval = max(1.0, settings.source_request_interval_seconds)

    with WikidataEntityDataFetcher(
        user_agent=settings.wikidata_user_agent,
        interval_seconds=interval,
    ) as wikidata:
        manifest["wikidata_robots_sha256"] = wikidata.robots_sha256
        for film in manifest["films"]:
            existing_path = film.get("wikidata_snapshot_path")
            if existing_path and film.get("wikidata_status") == "captured":
                snapshot_path = output_dir / existing_path
                payload = snapshot_path.read_bytes()
                if sha256(payload).hexdigest() != film.get("wikidata_sha256"):
                    raise CatalogPilotCaptureError(f"Wikidata snapshot hash mismatch for {film['qid']}.")
            else:
                try:
                    capture = wikidata.fetch(film["qid"])
                    relative_path, digest = _source_file(output_dir, "wikidata", film["qid"], capture.payload, ".json")
                    film.update({
                        "wikidata_status": "captured",
                        "wikidata_snapshot_path": relative_path,
                        "wikidata_sha256": digest,
                        "wikidata_revision": capture.entity["lastrevid"],
                        "wikidata_capture_url": capture.canonical_url,
                    })
                    payload = capture.payload
                except Exception as exc:
                    film.update({"capture_status": "failed", "error": f"{type(exc).__name__}: {exc}"[:1000]})
                    _write_checkpoint(manifest_path, manifest)
                    raise
            entity = entity_from_entitydata(json.loads(payload), film["qid"])
            sitelink = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
            title_matches = title_score(entity, film["title"]) > 0
            type_matches = is_film(entity)
            year_matches = is_film_in_year(entity, film["year"])
            film.update({
                "wikidata_label_en": entity.get("labels", {}).get("en", {}).get("value"),
                "enwiki_title": sitelink,
                "wikidata_film_type_ids": sorted(entity_ids(entity.get("claims", {}).get("P31", []))),
                "wikidata_publication_years": sorted(release_years(entity.get("claims", {}).get("P577", []))),
                "identity_checks": {
                    "english_label_or_alias_matches_input": title_matches,
                    "wikidata_film_type_present": type_matches,
                    "wikidata_release_year_matches_input": year_matches,
                    "english_wikipedia_sitelink_present": bool(sitelink),
                },
            })
            film["identity_status"] = "verified" if all((title_matches, type_matches, year_matches, sitelink)) else "review_required"
            film["capture_status"] = "identity_checked"
            _write_checkpoint(manifest_path, manifest)

    with WikipediaArticleFetcher(user_agent=settings.wikidata_user_agent, interval_seconds=interval) as wikipedia:
        manifest["wikipedia_robots_sha256"] = wikipedia.robots_sha256
        _write_checkpoint(manifest_path, manifest)
        for film in manifest["films"]:
            if film.get("identity_status") != "verified":
                continue
            existing_path = film.get("wikipedia_snapshot_path")
            if existing_path and film.get("wikipedia_status") == "captured":
                html_path = output_dir / existing_path
                html = html_path.read_bytes()
                if sha256(html).hexdigest() != film.get("wikipedia_sha256"):
                    raise CatalogPilotCaptureError(f"Wikipedia snapshot hash mismatch for {film['qid']}.")
                canonical_url = film["wikipedia_capture_url"]
            else:
                try:
                    html, canonical_url, status, media_type = wikipedia.fetch(article_url(film["enwiki_title"]))
                    relative_path, digest = _source_file(output_dir, "wikipedia", film["qid"], html, ".html")
                    film.update({
                        "wikipedia_status": "captured",
                        "wikipedia_snapshot_path": relative_path,
                        "wikipedia_sha256": digest,
                        "wikipedia_capture_url": canonical_url,
                        "wikipedia_http_status": status,
                        "wikipedia_media_type": media_type,
                        "wikipedia_bytes": len(html),
                    })
                except Exception as exc:
                    film.update({"capture_status": "failed", "error": f"{type(exc).__name__}: {exc}"[:1000]})
                    _write_checkpoint(manifest_path, manifest)
                    raise
            document = parse_article_html(html, canonical_url=canonical_url, expected_qid=film["qid"])
            passage_payload = json.dumps({
                "schema": f"cinegraph.wikipedia-passage-extraction/{PARSER_VERSION.rsplit('-v', 1)[-1]}",
                "source_snapshot_sha256": film["wikipedia_sha256"],
                "source_revision": document.metadata.revision_id,
                "parser_version": document.parser_version,
                "passages": [
                    {
                        "section_locator": passage.section_locator,
                        "section_title": passage.section_title,
                        "ordinal": passage.ordinal,
                        "content": passage.content,
                        "citation_markers": list(passage.citation_markers),
                        "citation_positions": [
                            {"marker_id": marker, "paragraph_index": paragraph_index,
                             "char_offset": char_offset}
                            for marker, paragraph_index, char_offset in passage.citation_positions
                        ],
                        "content_sha256": passage.content_hash,
                    }
                    for passage in document.passages
                ],
            }, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            derivative_path, derivative_hash = _source_file(
                output_dir, f"wikipedia-passages-v{PARSER_VERSION.rsplit('-v', 1)[-1]}",
                film["qid"], passage_payload, ".json",
            )
            film.update({
                "wikipedia_title_resolved": document.metadata.title,
                "wikipedia_page_id": document.metadata.page_id,
                "wikipedia_revision": document.metadata.revision_id,
                "passage_count": len(document.passages),
                "section_counts": _section_counts(document.passages),
                "passage_derivative_path": derivative_path,
                "passage_derivative_sha256": derivative_hash,
                "parser_version": document.parser_version,
                "wikipedia_license": "CC BY-SA 4.0",
                "wikipedia_attribution_url": canonical_url,
                "wikidata_license": "CC0 1.0",
                "wikidata_attribution_url": f"https://www.wikidata.org/wiki/{film['qid']}",
            })
            film["wikipedia_status"] = "captured"
            film["capture_status"] = "complete"
            _write_checkpoint(manifest_path, manifest)

    _write_checkpoint(manifest_path, manifest)
    return manifest


def _section_counts(passages: tuple[Any, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for passage in passages:
        counts[passage.section_title] = counts.get(passage.section_title, 0) + 1
    return dict(sorted(counts.items()))


def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Capture a small frozen title selection to local, resumable source snapshots."
    )
    parser.add_argument("selection", type=Path, help="Frozen catalog pilot JSON with title/year/QID candidates")
    parser.add_argument("--output", type=Path, required=True, help="Ignored local output directory for captures and report")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    try:
        report = capture_catalog_pilot(args.selection, args.output, limit=args.limit)
    except (CatalogPilotCaptureError, OSError, ValueError, RuntimeError) as exc:
        print(f"catalog pilot capture stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps({
        "report_path": str((args.output.resolve() / "capture-manifest.json")),
        "run_status": report.get("run_status"),
        "counts": report.get("counts"),
    }, indent=2, sort_keys=True))
    if report.get("run_status") != "complete":
        raise SystemExit(2)
