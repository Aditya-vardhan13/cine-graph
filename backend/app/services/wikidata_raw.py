"""Raw CC0 Wikidata snapshot adapter for a manifest of already-selected QIDs.

It deliberately does not discover titles from IMDb or scrape HTML. It records
the raw entity JSON before extracting source-shaped statements, giving later
normalizers a stable replay point.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DataSource, RawIngestionRun, SourceAccessPolicy
from app.services.raw_snapshots import source_assertion, source_object, snapshot
from app.services.wikidata import SOURCE_URL, source_for_wikidata

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
ADAPTER_VERSION = "wikidata-entity-json-v1"
QID = re.compile(r"Q\d+")


class RawWikidataError(RuntimeError):
    pass


def wikidata_api_policy(db: Session, source: DataSource) -> SourceAccessPolicy:
    policy = db.query(SourceAccessPolicy).filter_by(source_id=source.id, access_mode="api").one_or_none()
    if policy:
        policy.max_requests_per_minute = get_settings().source_requests_per_minute
        return policy
    policy = SourceAccessPolicy(
        source_id=source.id,
        access_mode="api",
        policy_url="https://www.wikidata.org/wiki/Wikidata:Data_access",
        robots_url="https://www.wikidata.org/robots.txt",
        robots_decision="documented_api_route",
        allowed_paths=[WIKIDATA_API],
        required_user_agent=True,
        max_requests_per_minute=get_settings().source_requests_per_minute,
        max_concurrency=1,
        decision="allowed",
        decision_notes="CC0 structured data through the documented API; identifying user agent, sequential batches and stop-on-denial policy required.",
    )
    db.add(policy)
    db.flush()
    return policy


def entities_from_response(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Extract valid entities from a retained Wikidata API payload."""
    raw_entities = payload.get("entities", {})
    entity_values = raw_entities.values() if isinstance(raw_entities, dict) else raw_entities
    return {
        entity["id"]: entity
        for entity in entity_values
        if isinstance(entity, dict) and entity.get("id") and "missing" not in entity
    }


def fetch_entities(qids: list[str]) -> dict[str, dict[str, Any]]:
    if not qids or any(not QID.fullmatch(qid) for qid in qids):
        raise RawWikidataError("A raw Wikidata run requires one or more QIDs.")
    headers = {"User-Agent": get_settings().wikidata_user_agent, "Accept-Encoding": "gzip, deflate"}
    entities: dict[str, dict[str, Any]] = {}
    with httpx.Client(timeout=60, headers=headers) as client:
        for start in range(0, len(qids), 50):
            response = client.get(WIKIDATA_API, params={
                "action": "wbgetentities", "ids": "|".join(qids[start:start + 50]),
                "format": "json", "formatversion": "2",
                "languages": "en",
            })
            if response.status_code in {401, 403}:
                raise RawWikidataError(f"Wikidata denied the request ({response.status_code}); stopping.")
            if response.status_code == 429:
                raise RawWikidataError("Wikidata rate-limited the run; stop and retry after the supplied delay.")
            response.raise_for_status()
            entities.update(entities_from_response(response.json()))
            if start + 50 < len(qids):
                time.sleep(1)
    return entities


def label(entity: dict[str, Any]) -> str:
    return entity.get("labels", {}).get("en", {}).get("value") or entity["id"]


def extract_assertions(db: Session, snapshot_id, entity: dict[str, Any]) -> int:
    inserted = 0
    for property_id, statements in entity.get("claims", {}).items():
        for position, statement in enumerate(statements):
            if source_assertion(
                db,
                source_snapshot_id=snapshot_id,
                statement_locator=f"claims.{property_id}[{position}]",
                source_property=property_id,
                raw_subject={"wikidata_id": entity["id"], "label": label(entity)},
                raw_value=statement.get("mainsnak", {}),
                raw_qualifiers=statement.get("qualifiers", {}),
                source_rank=statement.get("rank"),
                extractor_version=ADAPTER_VERSION,
            ):
                inserted += 1
    return inserted


def ingest_entities(
    db: Session,
    entities: dict[str, dict[str, Any]],
    manifest_uri: str | None = None,
    *,
    snapshot_root: str | Path | None = None,
) -> dict[str, int]:
    source: DataSource = source_for_wikidata(db)
    policy = wikidata_api_policy(db, source)
    if policy.decision != "allowed":
        raise RawWikidataError("The registered Wikidata API policy is not approved; refusing to ingest.")
    run = RawIngestionRun(
        source_id=source.id,
        access_policy_id=policy.id,
        adapter_name="wikidata_entity_json",
        adapter_version=ADAPTER_VERSION,
        manifest_uri=manifest_uri,
        status="running",
        records_requested=len(entities),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    stats = {"objects": 0, "snapshots": 0, "source_assertions": 0}
    for qid, entity in entities.items():
        item = source_object(
            db, source=source, external_id=qid, object_kind="wikibase_item",
            canonical_url=f"{SOURCE_URL}wiki/{qid}",
        )
        stats["objects"] += 1
        payload = json.dumps(entity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        source_revision = str(entity.get("lastrevid")) if entity.get("lastrevid") else None
        stored_snapshot, created = snapshot(
            db, item=item, run=run, payload=payload, source_revision=source_revision,
            canonical_url=f"{SOURCE_URL}wiki/{qid}", license="CC0 1.0",
            attribution_url=f"{SOURCE_URL}wiki/{qid}", parser_version=ADAPTER_VERSION,
            storage_root=snapshot_root,
        )
        if not created:
            continue
        stats["snapshots"] += 1
        stats["source_assertions"] += extract_assertions(db, stored_snapshot.id, entity)
    run.records_snapshotted = stats["snapshots"]
    run.status = "complete"
    run.completed_at = datetime.now(timezone.utc)
    db.commit()
    return stats


def ingest_selected_qids(db: Session, qids: list[str], manifest_uri: str | None = None) -> dict[str, int]:
    """Verify the registered access decision before the network request."""
    source = source_for_wikidata(db)
    policy = wikidata_api_policy(db, source)
    if policy.decision != "allowed":
        raise RawWikidataError("The registered Wikidata API policy is not approved; refusing to fetch.")
    return ingest_entities(db, fetch_entities(qids), manifest_uri=manifest_uri)


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Snapshot selected CC0 Wikidata entities before normalization.")
    parser.add_argument("qids", nargs="+", help="Selected Wikidata QIDs; discovery remains a separate manifest step.")
    args = parser.parse_args()
    run_migrations()
    with SessionLocal() as db:
        print(ingest_selected_qids(db, args.qids))


if __name__ == "__main__":
    main()
