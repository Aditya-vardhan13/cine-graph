"""Validate and optionally replay retained English-pilot source captures.

The default is an offline dry run. Applying requires the local development
PostgreSQL catalog, an already-current schema, and exact pre-existing catalog
film identities. Wikipedia HTML is retained only as licensed source snapshots;
the replay does not write narrative passages or make them model-eligible.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.services.catalog_pilot_audit import audit_capture_bundle
from app.services.english_catalog_pilot_reconciliation import reconcile_english_pilot_captures
from app.services.wikipedia_article_html import parse_article_html, validate_article_url
from app.services.wikidata_raw import entity_from_entitydata


DEFAULT_PILOT = Path("data/evaluation/catalog-pilot-english100-v1.json")
DEFAULT_BATCHES = (
    Path("data/evaluation/catalog-intake/first10-v1"),
    Path("data/evaluation/catalog-intake/english100-rank11-100-v1"),
)


class EnglishPilotReplayError(ValueError):
    """A retained English-pilot capture is unsafe or incomplete to replay."""


@dataclass(frozen=True)
class EnglishPilotReplay:
    entities: dict[str, dict[str, Any]]
    payloads: dict[str, bytes]
    articles: dict[str, "RetainedWikipediaArticle"]
    catalog_ids: dict[str, str]
    report: dict[str, Any]


@dataclass(frozen=True)
class RetainedWikipediaArticle:
    qid: str
    canonical_url: str
    payload: bytes
    title: str
    page_id: int
    revision_id: int


def _path_within(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def _capture_path(batch: Path, relative: Any, *, qid: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise EnglishPilotReplayError(f"{qid}: capture manifest has no relative EntityData path.")
    candidate = batch / relative
    if not _path_within(candidate, batch):
        raise EnglishPilotReplayError(f"{qid}: capture path escapes its immutable batch directory.")
    # resolve()+containment alone still accepts a symlink that targets another
    # file inside the batch. Captures are immutable inputs; reject symlinks so
    # their manifest path cannot silently change what bytes are replayed.
    current = batch
    for part in Path(relative).parts:
        if part in {"", ".", ".."}:
            raise EnglishPilotReplayError(f"{qid}: capture path is not a normalized relative path.")
        current = current / part
        if current.is_symlink():
            raise EnglishPilotReplayError(f"{qid}: symlinked capture paths are not allowed.")
    if not candidate.is_file():
        raise EnglishPilotReplayError(f"{qid}: retained EntityData bytes are missing.")
    return candidate


def _validate_capture_policy(policy: Any, *, batch_name: str) -> None:
    if not isinstance(policy, dict):
        raise EnglishPilotReplayError(f"{batch_name}: capture policy is missing or less restrictive than required.")
    interval = policy.get("minimum_interval_seconds")
    if (type(policy.get("concurrency")) is not int
            or policy["concurrency"] != 1
            or isinstance(interval, bool)
            or not isinstance(interval, (int, float))
            or not math.isfinite(interval)
            or interval < 1.0
            or policy.get("robots_required") is not True
            or policy.get("stop_on_denial_or_rate_limit") is not True
            or policy.get("wikidata_route") != "known-QID Special:EntityData JSON only"
            or policy.get("wikipedia_route") != "known enwiki sitelink ordinary /wiki/ page only"):
        raise EnglishPilotReplayError(f"{batch_name}: capture policy is missing or less restrictive than required.")


def _validate_pilot_shape(pilot: Any) -> list[dict[str, Any]]:
    if (not isinstance(pilot, dict) or not isinstance(pilot.get("films"), list)
            or len(pilot["films"]) != 100):
        raise EnglishPilotReplayError("Frozen English pilot must contain exactly 100 film rows.")
    rows = pilot["films"]
    if any(not isinstance(row, dict) for row in rows):
        raise EnglishPilotReplayError("Frozen English pilot contains a malformed film row.")
    try:
        ranks = [row["selection_rank"] for row in rows]
        if any(not isinstance(rank, int) or isinstance(rank, bool) for rank in ranks):
            raise ValueError("selection ranks must be integers")
        if sorted(ranks) != list(range(1, 101)):
            raise ValueError("selection ranks must be unique and contiguous from 1 to 100")
        if any(not isinstance(row.get("catalog_film_id"), str) or not row["catalog_film_id"].strip()
               or not isinstance(row.get("wikidata_id"), str) or not row["wikidata_id"].strip()
               for row in rows):
            raise ValueError("every film must have a catalog ID and Wikidata QID")
    except (KeyError, TypeError, ValueError) as exc:
        raise EnglishPilotReplayError(f"Frozen English pilot rows are invalid: {exc}.") from exc
    return rows


def _validate_capture_manifest_shape(manifest: Any, *, batch_name: str) -> None:
    if (not isinstance(manifest, dict)
            or manifest.get("schema") != "cinegraph.catalog-pilot-capture/v1"
            or not isinstance(manifest.get("films"), list)
            or not manifest["films"]
            or any(not isinstance(row, dict) for row in manifest["films"])):
        raise EnglishPilotReplayError(f"{batch_name}: capture manifest has an invalid structure.")


def load_english_pilot_replay(
    project_root: Path,
    *,
    pilot_path: Path = DEFAULT_PILOT,
    batch_paths: tuple[Path, ...] = DEFAULT_BATCHES,
) -> EnglishPilotReplay:
    """Verify both capture bundles and load exact Wikidata JSON and Wikipedia HTML bytes."""
    project = project_root.resolve()
    evaluation_root = (project / "data/evaluation").resolve()
    pilot_file = (project / pilot_path).resolve()
    batches = tuple((project / batch).resolve() for batch in batch_paths)
    if not _path_within(pilot_file, evaluation_root) or not pilot_file.is_file():
        raise EnglishPilotReplayError("English pilot manifest must exist under local data/evaluation.")
    if len(batches) < 1 or any(not _path_within(batch, evaluation_root) for batch in batches):
        raise EnglishPilotReplayError("All capture batches must stay under local data/evaluation.")

    pilot_bytes = pilot_file.read_bytes()
    try:
        pilot = json.loads(pilot_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EnglishPilotReplayError("English pilot manifest is not valid JSON.") from exc
    _validate_pilot_shape(pilot)

    bundle_inputs: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    manifests: list[tuple[Path, bytes, dict[str, Any]]] = []
    for batch in batches:
        manifest_file = batch / "capture-manifest.json"
        if manifest_file.is_symlink() or not manifest_file.is_file():
            raise EnglishPilotReplayError(f"Missing capture manifest in {batch}.")
        manifest_bytes = manifest_file.read_bytes()
        try:
            manifest = json.loads(manifest_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise EnglishPilotReplayError(f"Capture manifest is not valid JSON for {batch.name}.") from exc
        _validate_capture_manifest_shape(manifest, batch_name=batch.name)
        try:
            audit = audit_capture_bundle(batch)
        except (ValueError, RuntimeError) as exc:
            raise EnglishPilotReplayError(f"Capture audit failed for {batch.name}: {exc}") from exc
        _validate_capture_policy(manifest.get("capture_policy"), batch_name=batch.name)
        manifests.append((batch, manifest_bytes, manifest))
        bundle_inputs.append((batch.name, manifest, audit))

    pilot_digest = sha256(pilot_bytes).hexdigest()
    try:
        reconciliation = reconcile_english_pilot_captures(
            pilot, bundle_inputs, pilot_sha256=pilot_digest,
        )
    except ValueError as exc:
        raise EnglishPilotReplayError(f"Capture batches do not match the frozen English pilot: {exc}") from exc

    robots_hashes = {
        batch.get("wikidata_robots_sha256") for batch in reconciliation["batches"]
    }
    if len(robots_hashes) != 1 or not next(iter(robots_hashes)):
        raise EnglishPilotReplayError("Capture batches do not share one recorded Wikidata robots.txt hash.")

    pilot_by_rank = {row["selection_rank"]: row for row in pilot["films"]}
    manifest_by_rank = {
        row["selection_rank"]: (batch, row)
        for batch, _manifest_bytes, manifest in manifests
        for row in manifest["films"]
    }
    entities: dict[str, dict[str, Any]] = {}
    payloads: dict[str, bytes] = {}
    articles: dict[str, RetainedWikipediaArticle] = {}
    catalog_ids: dict[str, str] = {}
    for rank in range(1, reconciliation["expected_films"] + 1):
        pilot_row = pilot_by_rank[rank]
        batch, capture_row = manifest_by_rank[rank]
        qid = capture_row["qid"]
        if qid in entities:
            raise EnglishPilotReplayError(f"QID {qid} is duplicated in the selected pilot.")
        if (capture_row.get("wikidata_license") != "CC0 1.0"
                or capture_row.get("wikidata_status") != "captured"
                or capture_row.get("identity_status") != "verified"):
            raise EnglishPilotReplayError(f"{qid}: capture is not verified CC0 Wikidata EntityData.")
        payload_path = _capture_path(batch, capture_row.get("wikidata_snapshot_path"), qid=qid)
        payload = payload_path.read_bytes()
        if sha256(payload).hexdigest() != capture_row.get("wikidata_sha256"):
            raise EnglishPilotReplayError(f"{qid}: raw EntityData SHA-256 does not match its manifest.")
        try:
            entity = entity_from_entitydata(json.loads(payload), qid)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise EnglishPilotReplayError(f"{qid}: retained EntityData is invalid: {exc}") from exc
        if entity.get("lastrevid") != capture_row.get("wikidata_revision"):
            raise EnglishPilotReplayError(f"{qid}: source revision differs from the capture manifest.")
        if qid != pilot_row.get("wikidata_id"):
            raise EnglishPilotReplayError(f"{qid}: QID differs from frozen pilot rank {rank}.")
        if (capture_row.get("capture_status") != "complete"
                or capture_row.get("wikipedia_status") != "captured"
                or capture_row.get("wikipedia_http_status") != 200
                or capture_row.get("wikipedia_media_type") != "text/html"
                or capture_row.get("wikipedia_license") != "CC BY-SA 4.0"):
            raise EnglishPilotReplayError(f"{qid}: retained Wikipedia article capture is incomplete or unlicensed.")
        article_path = _capture_path(batch, capture_row.get("wikipedia_snapshot_path"), qid=qid)
        article_payload = article_path.read_bytes()
        article_hash = sha256(article_payload).hexdigest()
        if (article_hash != capture_row.get("wikipedia_sha256")
                or len(article_payload) != capture_row.get("wikipedia_bytes")):
            raise EnglishPilotReplayError(f"{qid}: raw Wikipedia article bytes do not match the capture manifest.")
        try:
            canonical_url = validate_article_url(capture_row.get("wikipedia_capture_url", ""))
            article = parse_article_html(article_payload, canonical_url=canonical_url, expected_qid=qid)
        except (ValueError, TypeError) as exc:
            raise EnglishPilotReplayError(f"{qid}: retained Wikipedia article failed identity parsing: {exc}") from exc
        if (article.metadata.title != capture_row.get("wikipedia_title_resolved")
                or article.metadata.page_id != capture_row.get("wikipedia_page_id")
                or article.metadata.revision_id != capture_row.get("wikipedia_revision")):
            raise EnglishPilotReplayError(f"{qid}: Wikipedia page metadata differs from its capture manifest.")
        entities[qid] = entity
        payloads[qid] = payload
        articles[qid] = RetainedWikipediaArticle(
            qid=qid, canonical_url=canonical_url, payload=article_payload,
            title=article.metadata.title, page_id=article.metadata.page_id,
            revision_id=article.metadata.revision_id,
        )
        catalog_ids[qid] = str(pilot_row["catalog_film_id"])

    wikipedia_robots_hashes = {
        batch.get("wikipedia_robots_sha256") for batch in reconciliation["batches"]
    }
    if (len(wikipedia_robots_hashes) != 1
            or not isinstance(next(iter(wikipedia_robots_hashes)), str)
            or len(next(iter(wikipedia_robots_hashes))) != 64
            or any(char not in "0123456789abcdef" for char in next(iter(wikipedia_robots_hashes)))):
        raise EnglishPilotReplayError("Capture batches do not share one valid Wikipedia robots.txt hash.")

    manifest_inputs = {
        "schema": "cinegraph.english-pilot-source-inputs/v2",
        "pilot_sha256": pilot_digest,
        "capture_manifests": [
            {"path": str((batch / "capture-manifest.json").relative_to(project)),
             "sha256": sha256(manifest_bytes).hexdigest()}
            for batch, manifest_bytes, _manifest in manifests
        ],
        "wikidata_robots_sha256": next(iter(robots_hashes)),
        "wikipedia_robots_sha256": next(iter(wikipedia_robots_hashes)),
    }
    combined_manifest = sha256(json.dumps(
        manifest_inputs, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    report = {
        "schema": "cinegraph.english-pilot-source-replay/v2",
        "ready_for_database_preflight": True,
        "films": len(entities),
        "wikidata_payload_bytes": sum(map(len, payloads.values())),
        "wikipedia_article_count": len(articles),
        "wikipedia_article_bytes": sum(len(article.payload) for article in articles.values()),
        "pilot_sha256": pilot_digest,
        "combined_manifest_sha256": combined_manifest,
        "robots_sha256": next(iter(robots_hashes)),
        "manifest_inputs": manifest_inputs,
        "captures": [
            {"qid": qid, "catalog_film_id": catalog_ids[qid],
             "revision": entity.get("lastrevid"),
             "wikidata_sha256": sha256(payloads[qid]).hexdigest(),
             "wikipedia_source_url": articles[qid].canonical_url,
             "wikipedia_license": "CC BY-SA 4.0",
             "wikipedia_title": articles[qid].title,
             "wikipedia_page_id": articles[qid].page_id,
             "wikipedia_revision": articles[qid].revision_id,
             "wikipedia_sha256": sha256(articles[qid].payload).hexdigest()}
            for qid, entity in entities.items()
        ],
        "captured_passages_not_ingested": True,
        "wikipedia_prose_chunks_not_ingested": True,
        "wikipedia_prose_not_model_eligible": True,
        "limitations": [
            "This verifies retained capture identity and bytes, not factual accuracy or human rights review.",
            "A successful dry run does not prove that catalog QIDs still map to the expected database IDs.",
            "Applying requires an explicit local-only PostgreSQL action and an exact database identity preflight.",
        ],
    }
    return EnglishPilotReplay(entities, payloads, articles, catalog_ids, report)


def _preflight_database(db, replay: EnglishPilotReplay) -> None:
    from app.migrations import require_current_schema
    from app.models import CanonicalEntity

    settings = get_settings()
    url = make_url(settings.database_url)
    if settings.environment not in {"development", "local"}:
        raise EnglishPilotReplayError("Applying the local English pilot is restricted to development/local.")
    if (url.get_backend_name() != "postgresql" or url.database != "cinegraph"
            or url.host != "db" or url.port not in {None, 5432}):
        raise EnglishPilotReplayError("Apply target must be the local PostgreSQL database named cinegraph.")
    shared_snapshot_root = Path(settings.raw_snapshot_root).expanduser().resolve()
    if shared_snapshot_root != Path("/var/lib/cinegraph/raw-snapshots"):
        raise EnglishPilotReplayError(
            "Apply must run in the Compose API container with the shared raw_snapshots volume mounted."
        )
    if not shared_snapshot_root.is_dir():
        raise EnglishPilotReplayError("Compose shared raw_snapshots volume is not mounted.")
    if not os.access(shared_snapshot_root, os.W_OK):
        raise EnglishPilotReplayError("Compose shared raw_snapshots volume is not writable.")
    require_current_schema()
    by_qid = {
        entity.wikidata_id: entity
        for entity in db.scalars(select(CanonicalEntity).where(
            CanonicalEntity.wikidata_id.in_(set(replay.catalog_ids)),
        ))
        if entity.wikidata_id
    }
    if set(by_qid) != set(replay.catalog_ids):
        missing = sorted(set(replay.catalog_ids) - set(by_qid))
        raise EnglishPilotReplayError(f"Catalog is missing exact pilot QIDs: {missing[:10]}.")
    mismatches = [qid for qid, expected_id in replay.catalog_ids.items()
                  if str(by_qid[qid].id) != expected_id or by_qid[qid].entity_kind != "film"]
    if mismatches:
        raise EnglishPilotReplayError(f"Pilot QIDs do not map to their frozen film IDs: {mismatches[:10]}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", type=Path, default=DEFAULT_PILOT)
    parser.add_argument("--first-ten", type=Path, default=DEFAULT_BATCHES[0])
    parser.add_argument("--rank-11-100", type=Path, default=DEFAULT_BATCHES[1])
    parser.add_argument(
        "--manifest-output", type=Path,
        default=Path("manifests/english100-source-replay-manifest-v2.json"),
    )
    parser.add_argument("--apply", action="store_true", help="Write only to local PostgreSQL cinegraph after exact identity preflight.")
    args = parser.parse_args()
    replay = load_english_pilot_replay(
        Path.cwd(), pilot_path=args.pilot,
        batch_paths=(args.first_ten, args.rank_11_100),
    )
    result: dict[str, Any] = {"mode": "dry-run", **replay.report}
    if args.apply:
        from app.db import SessionLocal
        from app.services.source_assertion_projection import project_source_assertions
        from app.services.wikidata_raw import ingest_entities
        from app.services.wikipedia_raw import ingest_captured_article

        with SessionLocal() as db:
            _preflight_database(db, replay)
            snapshot_root = Path(get_settings().raw_snapshot_root).expanduser().resolve()
            output_path = (snapshot_root / args.manifest_output).resolve()
            if not _path_within(output_path, snapshot_root):
                raise EnglishPilotReplayError("Replay manifest output must stay under the shared local snapshot volume.")
            manifest_bytes = (json.dumps(replay.report, sort_keys=True, indent=2) + "\n").encode("utf-8")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                if output_path.read_bytes() != manifest_bytes:
                    raise EnglishPilotReplayError(
                        "Refusing to overwrite a different replay manifest; choose a new versioned output path."
                    )
            else:
                output_path.write_bytes(manifest_bytes)
            ingestion = ingest_entities(
                db, replay.entities, output_path.as_uri(),
                raw_payloads=replay.payloads,
                snapshot_root=snapshot_root,
                robots_sha256=replay.report["robots_sha256"],
                manifest_sha256=sha256(manifest_bytes).hexdigest(),
            )
            article_stats = {"resolved": 0, "snapshots": 0, "source_assertions": 0}
            for qid, article in replay.articles.items():
                item = ingest_captured_article(
                    db, payload=article.payload, canonical_url=article.canonical_url,
                    media_type="text/html", expected_qid=qid,
                    robots_sha256=replay.report["wikipedia_robots_sha256"],
                    manifest_uri=output_path.as_uri(), manifest_sha256=sha256(manifest_bytes).hexdigest(),
                    storage_root=snapshot_root,
                )
                for key in article_stats:
                    article_stats[key] += item.get(key, 0)
            projection = project_source_assertions(db, qids=set(replay.entities))
        result.update({"mode": "applied", "replay_manifest_uri": output_path.as_uri(),
                   "wikidata_ingestion": ingestion, "wikipedia_article_ingestion": article_stats,
                   "projection": projection})
    print(json.dumps(result, indent=2, sort_keys=True, default=dict))


if __name__ == "__main__":
    main()
