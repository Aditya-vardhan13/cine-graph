"""Raw CC0 Wikidata snapshot adapter for a manifest of already-selected QIDs.

It deliberately does not discover titles from IMDb or scrape HTML. It records
the raw entity JSON before extracting source-shaped statements, giving later
normalizers a stable replay point.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DataSource, RawIngestionRun, SourceAccessPolicy, SourceAssertion, SourceObject, SourceSnapshot
from app.services.raw_snapshots import link_snapshot_to_run, source_assertion, source_object, snapshot
from app.services.wikidata import SOURCE_URL, source_for_wikidata

WIKIDATA_ENTITY_DATA = "https://www.wikidata.org/wiki/Special:EntityData"
WIKIDATA_ROBOTS_URL = "https://www.wikidata.org/robots.txt"
ADAPTER_VERSION = "wikidata-entitydata-json-v2"
QID = re.compile(r"Q\d+")
MAX_ENTITYDATA_BYTES = 25 * 1024 * 1024
MAX_ROBOTS_BYTES = 512 * 1024
MAX_REDIRECTS = 5
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_RESERVED = frozenset(":/?#[]@!$&'()*+,;=")


class RawWikidataError(RuntimeError):
    pass


@dataclass(frozen=True)
class EntityDataCapture:
    qid: str
    entity: dict[str, Any]
    payload: bytes
    canonical_url: str


def entitydata_url(qid: str) -> str:
    if not QID.fullmatch(qid):
        raise RawWikidataError("A Wikidata EntityData request requires a valid QID.")
    return f"{WIKIDATA_ENTITY_DATA}/{qid}.json"


def validate_entitydata_url(url: str) -> str:
    """Constrain redirects to the documented HTTPS JSON-suffix route."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise RawWikidataError("Wikidata EntityData URL has an invalid authority.") from exc
    host = (parts.hostname or "").casefold()
    if (parts.scheme != "https" or host != "www.wikidata.org"
            or parts.username or parts.password or port or parts.query or parts.fragment
            or not re.fullmatch(r"/wiki/Special:EntityData/Q\d+\.json", parts.path)):
        raise RawWikidataError("Only HTTPS Wikidata EntityData QID JSON URLs are supported.")
    return f"https://{host}{parts.path}"


def _robots_path(value: str, *, rule: bool) -> str:
    """Canonicalize paths per RFC 9309 while preserving robots wildcards."""
    result: list[str] = []
    index = 0
    while index < len(value):
        if value[index] == "%" and index + 2 < len(value) and re.fullmatch(r"[0-9A-Fa-f]{2}", value[index + 1:index + 3]):
            byte = int(value[index + 1:index + 3], 16)
            char = chr(byte)
            if char in _UNRESERVED:
                result.append(char)
            else:
                result.append(f"%{byte:02X}")
            index += 3
            continue
        char = value[index]
        if char in _UNRESERVED or char == "/" or (rule and char == "*") or (rule and char == "$" and index == len(value) - 1):
            result.append(char)
        elif char in _RESERVED or ord(char) > 0x7F:
            result.extend(f"%{byte:02X}" for byte in char.encode("utf-8"))
        else:
            result.append(char)
        index += 1
    return "".join(result)


def robots_allows(robots_text: str, *, user_agent: str, url: str) -> bool:
    """Evaluate the matching robots group using RFC 9309 path specificity.

    The stdlib parser normalizes reserved path characters and rule wildcards in
    a way that makes Wikidata's explicit colon-path `Allow` exception appear
    disallowed. This small evaluator implements only the standard UA groups,
    Allow/Disallow, `*`, `$`, and longest-match rules used by these sources.
    """
    path = _robots_path(urlsplit(url).path, rule=False)
    groups: list[tuple[list[str], list[tuple[str, bool]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, bool]] = []
    saw_rule = False

    def finish_group() -> None:
        nonlocal agents, rules, saw_rule
        if agents:
            groups.append((agents, rules))
        agents, rules, saw_rule = [], [], False

    for raw_line in robots_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.casefold()
        if field == "user-agent":
            if saw_rule:
                finish_group()
            agents.append(value.casefold())
        elif field in {"allow", "disallow"} and agents:
            saw_rule = True
            if value:
                rules.append((_robots_path(value, rule=True), field == "allow"))
    finish_group()

    product_token = user_agent.split(None, 1)[0].split("/", 1)[0].casefold()
    matched = [group_rules for group_agents, group_rules in groups if product_token in group_agents]
    if not matched:
        matched = [group_rules for group_agents, group_rules in groups if "*" in group_agents]
    matches: list[tuple[int, bool]] = []
    for group_rules in matched:
        for pattern, allowed in group_rules:
            anchored = pattern.endswith("$")
            body = pattern[:-1] if anchored else pattern
            regex = re.escape(body).replace(r"\*", ".*")
            if re.match(f"^{regex}{'$' if anchored else ''}", path):
                specificity = len(body.replace("*", ""))
                matches.append((specificity, allowed))
    if not matches:
        return True
    most_specific = max(length for length, _ in matches)
    return any(allowed for length, allowed in matches if length == most_specific)


class WikidataEntityDataFetcher:
    """Single-job EntityData client that checks robots and paces every request."""

    def __init__(self, *, user_agent: str, interval_seconds: float = 1.0,
                 timeout_seconds: float = 60.0) -> None:
        if not user_agent.strip():
            raise ValueError("A descriptive user-agent is required.")
        if not 1.0 <= interval_seconds <= 10.0:
            raise ValueError("Wikidata requests must be at least one second apart.")
        self.user_agent = user_agent
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.client: httpx.Client | None = None
        self.robots_text: str | None = None
        self.robots_sha256: str | None = None
        self._last_request_started: float | None = None

    def __enter__(self) -> "WikidataEntityDataFetcher":
        self.client = httpx.Client(
            timeout=self.timeout_seconds, follow_redirects=False,
            headers={"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate",
                     "Accept": "application/json,text/plain"},
        )
        try:
            status, headers, body = self._request(WIKIDATA_ROBOTS_URL, MAX_ROBOTS_BYTES)
        except httpx.HTTPError as exc:
            self.client.close()
            self.client = None
            raise RawWikidataError(f"Could not retrieve Wikidata robots.txt: {exc}") from exc
        except Exception:
            self.client.close()
            self.client = None
            raise
        if status != 200:
            self.client.close()
            self.client = None
            raise RawWikidataError(f"Wikidata robots.txt returned HTTP {status}; refusing capture.")
        self.robots_sha256 = sha256(body).hexdigest()
        self.robots_text = body.decode("utf-8", errors="replace")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def _pace(self) -> None:
        if self._last_request_started is not None:
            remaining = self.interval_seconds - (time.monotonic() - self._last_request_started)
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_started = time.monotonic()

    def _request(self, url: str, byte_limit: int) -> tuple[int, dict[str, str], bytes]:
        if self.client is None:
            raise RawWikidataError("WikidataEntityDataFetcher must be used as a context manager.")
        self._pace()
        with self.client.stream("GET", url) as response:
            headers = dict(response.headers)
            if response.status_code in {301, 302, 303, 307, 308}:
                return response.status_code, headers, b""
            body = bytearray()
            for block in response.iter_bytes():
                body.extend(block)
                if len(body) > byte_limit:
                    raise RawWikidataError(f"Wikidata response exceeded the {byte_limit}-byte safety limit.")
            return response.status_code, headers, bytes(body)

    def fetch(self, qid: str) -> EntityDataCapture:
        if self.robots_text is None:
            raise RawWikidataError("Wikidata robots.txt has not been loaded for this capture job.")
        current = entitydata_url(qid)
        for redirect_count in range(MAX_REDIRECTS + 1):
            if not robots_allows(self.robots_text, user_agent=self.user_agent, url=current):
                raise RawWikidataError(f"Wikidata robots.txt disallows EntityData URL: {current}")
            try:
                status, headers, body = self._request(current, MAX_ENTITYDATA_BYTES)
            except httpx.HTTPError as exc:
                raise RawWikidataError(f"Wikidata EntityData request failed: {exc}") from exc
            if status in {301, 302, 303, 307, 308}:
                if redirect_count == MAX_REDIRECTS:
                    raise RawWikidataError("Wikidata EntityData exceeded the redirect limit.")
                location = headers.get("location")
                if not location:
                    raise RawWikidataError("Wikidata returned a redirect without a Location header.")
                try:
                    current = validate_entitydata_url(urljoin(current, location))
                except RawWikidataError as exc:
                    raise RawWikidataError(f"Wikidata redirected outside the permitted JSON route: {location}") from exc
                continue
            if status in {401, 403, 429}:
                raise RawWikidataError(f"Wikidata returned HTTP {status}; capture stopped without retry.")
            if status != 200:
                raise RawWikidataError(f"Wikidata returned HTTP {status}; capture stopped.")
            media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                raise RawWikidataError(f"Expected Wikidata JSON, received {media_type or 'unknown media type'}.")
            try:
                entity = entity_from_entitydata(json.loads(body), qid)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise RawWikidataError("Wikidata EntityData response is not valid JSON.") from exc
            return EntityDataCapture(qid, entity, body, current)
        raise RawWikidataError("Wikidata EntityData redirect resolution terminated unexpectedly.")


def wikidata_entitydata_policy(
    db: Session, source: DataSource, *, robots_sha256: str | None = None,
) -> SourceAccessPolicy:
    policy = db.query(SourceAccessPolicy).filter_by(source_id=source.id, access_mode="api").one_or_none()
    if policy:
        policy.max_requests_per_minute = min(get_settings().source_requests_per_minute, 60)
        policy.policy_url = "https://www.wikidata.org/wiki/Help:Data_access"
        policy.robots_url = "https://www.wikidata.org/robots.txt"
        policy.robots_decision = "allow_extension_route"
        policy.allowed_paths = [f"{WIKIDATA_ENTITY_DATA}/*.json"]
        policy.required_user_agent = True
        policy.max_concurrency = 1
        policy.decision_notes = (
            "Pinned/current entity JSON through the documented Special:EntityData route. "
            "The JSON-suffix route is explicitly allowed by Wikidata robots.txt; use an "
            "identifying user agent, one request at a time, at least one second apart, "
            "and stop on denial or rate limiting. The generic /w/api.php route is not used."
        )
        if robots_sha256:
            policy.policy_revision = f"robots-sha256:{robots_sha256}"
        return policy
    policy = SourceAccessPolicy(
        source_id=source.id,
        access_mode="api",
        policy_url="https://www.wikidata.org/wiki/Help:Data_access",
        robots_url="https://www.wikidata.org/robots.txt",
        robots_decision="allow_extension_route",
        allowed_paths=[f"{WIKIDATA_ENTITY_DATA}/*.json"],
        required_user_agent=True,
        max_requests_per_minute=min(get_settings().source_requests_per_minute, 60),
        max_concurrency=1,
        decision="allowed",
        decision_notes=(
            "Pinned/current entity JSON through the documented Special:EntityData route. "
            "The JSON-suffix route is explicitly allowed by Wikidata robots.txt; use an "
            "identifying user agent, one request at a time, at least one second apart, "
            "and stop on denial or rate limiting. The generic /w/api.php route is not used."
        ),
    )
    db.add(policy)
    db.flush()
    if robots_sha256:
        policy.policy_revision = f"robots-sha256:{robots_sha256}"
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


def entity_from_entitydata(payload: dict[str, Any], qid: str) -> dict[str, Any]:
    """Select exactly the requested item from a Wikibase EntityData response."""
    entities = entities_from_response(payload)
    entity = entities.get(qid)
    if entity is None and payload.get("id") == qid:
        entity = payload
    if entity is None or entity.get("lastrevid") is None:
        raise RawWikidataError(f"EntityData response did not contain the requested revisioned entity {qid}.")
    return entity


def fetch_entities(qids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch known QIDs sequentially through the robots-checked JSON route.

    This helper is for read-only identity resolution. Ingestion must use
    ``ingest_selected_qids`` so each exact response is persisted before the
    next network request begins.
    """
    unique_qids = list(dict.fromkeys(qids))
    if not unique_qids or any(not QID.fullmatch(qid) for qid in unique_qids):
        raise RawWikidataError("A Wikidata read requires one or more valid QIDs.")
    settings = get_settings()
    entities: dict[str, dict[str, Any]] = {}
    with WikidataEntityDataFetcher(
        user_agent=settings.wikidata_user_agent,
        interval_seconds=max(1.0, settings.source_request_interval_seconds),
    ) as fetcher:
        for qid in unique_qids:
            capture = fetcher.fetch(qid)
            entities[qid] = capture.entity
    return entities


def label(entity: dict[str, Any]) -> str:
    return entity.get("labels", {}).get("en", {}).get("value") or entity["id"]


def extract_english_label(db: Session, snapshot_id, entity: dict[str, Any]) -> int:
    """Append an explicitly present source label without fabricating a QID name."""
    english = entity.get("labels", {}).get("en", {})
    text = english.get("value") if isinstance(english, dict) else None
    if isinstance(text, str) and text.strip():
        return int(source_assertion(
            db, source_snapshot_id=snapshot_id, statement_locator="labels.en",
            source_property="wikidata:label:en", raw_subject={"wikidata_id": entity["id"]},
            raw_value={"language": "en", "text": text}, raw_qualifiers={},
            source_rank=None, extractor_version=ADAPTER_VERSION,
        ))
    return 0


def persist_english_label_capture(
    db: Session, *, source: DataSource, run: RawIngestionRun, qid: str,
    entity: dict[str, Any], payload: bytes, canonical_url: str | None = None,
    snapshot_root: str | Path | None = None,
) -> tuple[bool, int]:
    """Retain a verified EntityData response while extracting only its label.

    Credit-name enrichment needs the immutable source payload and a source-linked
    ``labels.en`` assertion, not every unrelated claim on each person item.
    This bounded path avoids turning a label lookup into a second bulk fact
    ingestion while preserving the same evidence chain as full entity capture.
    """
    if not QID.fullmatch(qid) or entity.get("id") != qid:
        raise RawWikidataError(f"Parsed Wikidata entity does not match requested QID {qid}.")
    try:
        retained_entity = entity_from_entitydata(json.loads(payload), qid)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RawWikidataError(f"Retained EntityData payload for {qid} is not valid JSON.") from exc
    if retained_entity != entity:
        raise RawWikidataError(f"Retained EntityData payload does not match parsed entity {qid}.")
    capture_url = canonical_url or entitydata_url(qid)
    item = source_object(
        db, source=source, external_id=qid, object_kind="wikibase_item",
        canonical_url=f"{SOURCE_URL}wiki/{qid}",
    )
    source_revision = str(entity.get("lastrevid")) if entity.get("lastrevid") else None
    stored_snapshot, created = snapshot(
        db, item=item, run=run, payload=payload, source_revision=source_revision,
        canonical_url=capture_url, license="CC0 1.0",
        attribution_url=f"{SOURCE_URL}wiki/{qid}", parser_version=ADAPTER_VERSION,
        storage_root=snapshot_root,
    )
    assertions_created = extract_english_label(db, stored_snapshot.id, entity)
    return created, assertions_created


def ingest_selected_credit_labels(
    db: Session, qids: list[str], manifest_uri: str | None = None,
) -> dict[str, int]:
    """Capture source-linked English labels only for selected credit targets.

    A prior successful EntityData snapshot is reused, including backfilling its
    label assertion from exact retained bytes when necessary. Only QIDs with no
    retained snapshot cause network requests. Each new response is committed
    before the next robots-checked, sequential request.
    """
    unique_qids = list(dict.fromkeys(qids))
    if not unique_qids or any(not QID.fullmatch(qid) for qid in unique_qids):
        raise RawWikidataError("A credit-label run requires one or more valid Wikidata QIDs.")
    source = source_for_wikidata(db)
    policy = wikidata_entitydata_policy(db, source)
    if policy.decision != "allowed":
        raise RawWikidataError("The registered Wikidata EntityData policy is not approved; refusing to fetch.")
    run = start_ingestion_run(
        db, source=source, policy=policy, requested=len(unique_qids), manifest_uri=manifest_uri,
    )
    stats = {"targets": len(unique_qids), "snapshots_created": 0,
             "source_assertions_created": 0, "snapshots_reused": 0,
             "without_english_label": 0}
    latest_by_qid: dict[str, SourceSnapshot | None] = {}
    for qid in unique_qids:
        item = db.scalar(select(SourceObject).where(
            SourceObject.source_id == source.id, SourceObject.external_id == qid,
        ))
        latest_by_qid[qid] = db.scalar(select(SourceSnapshot).where(
            SourceSnapshot.source_object_id == item.id if item else False,
            SourceSnapshot.fetch_status == "success",
        ).order_by(SourceSnapshot.retrieved_at.desc(), SourceSnapshot.id.desc()).limit(1))

    missing_qids = [qid for qid, item in latest_by_qid.items() if item is None]
    settings = get_settings()
    fetcher_context = (
        WikidataEntityDataFetcher(
            user_agent=settings.wikidata_user_agent,
            interval_seconds=max(1.0, settings.source_request_interval_seconds),
        ) if missing_qids else nullcontext(None)
    )
    processed = 0
    try:
        with fetcher_context as fetcher:
            if fetcher is not None:
                policy = wikidata_entitydata_policy(db, source, robots_sha256=fetcher.robots_sha256)
            for qid in unique_qids:
                retained = latest_by_qid[qid]
                if retained is not None:
                    link_snapshot_to_run(db, run.id, retained.id, "reused")
                    stats["snapshots_reused"] += 1
                    exists = db.scalar(select(SourceAssertion.id).where(
                        SourceAssertion.source_snapshot_id == retained.id,
                        SourceAssertion.source_property == "wikidata:label:en",
                        SourceAssertion.statement_locator == "labels.en",
                    ))
                    if not exists:
                        storage = urlsplit(retained.storage_uri or "")
                        if storage.scheme != "file":
                            raise RawWikidataError(f"Retained local EntityData bytes are unavailable for {qid}.")
                        payload = Path(unquote(storage.path)).read_bytes()
                        if sha256(payload).hexdigest() != retained.content_hash:
                            raise RawWikidataError(f"Retained EntityData snapshot hash mismatch for {qid}.")
                        entity = entity_from_entitydata(json.loads(payload), qid)
                        stats["source_assertions_created"] += extract_english_label(db, retained.id, entity)
                        stats["without_english_label"] += not bool(
                            entity.get("labels", {}).get("en", {}).get("value")
                        )
                    else:
                        label_value = db.scalar(select(SourceAssertion.raw_value).where(
                            SourceAssertion.source_snapshot_id == retained.id,
                            SourceAssertion.source_property == "wikidata:label:en",
                            SourceAssertion.statement_locator == "labels.en",
                        ))
                        if not label_value or not label_value.get("text"):
                            stats["without_english_label"] += 1
                    processed += 1
                    db.commit()
                    continue
                if fetcher is None:
                    raise RawWikidataError("Missing EntityData target has no active policy-checked fetcher.")
                capture = fetcher.fetch(qid)
                created, assertions_created = persist_english_label_capture(
                    db, source=source, run=run, qid=qid, entity=capture.entity,
                    payload=capture.payload, canonical_url=capture.canonical_url,
                )
                stats["snapshots_created"] += int(created)
                stats["source_assertions_created"] += assertions_created
                stats["without_english_label"] += int(assertions_created == 0)
                run.records_snapshotted = stats["snapshots_created"]
                processed += 1
                db.commit()
            run.status = "complete"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        db.rollback()
        failed_run = db.get(RawIngestionRun, run.id)
        if failed_run:
            failed_run.status = "failed"
            failed_run.error_summary = f"{type(exc).__name__}: {exc}"[:1000]
            failed_run.records_snapshotted = stats["snapshots_created"]
            failed_run.records_failed = len(unique_qids) - processed
            failed_run.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise
    return stats


def extract_assertions(db: Session, snapshot_id, entity: dict[str, Any]) -> int:
    inserted = extract_english_label(db, snapshot_id, entity)
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


def persist_entity_capture(
    db: Session, *, source: DataSource, run: RawIngestionRun, qid: str,
    entity: dict[str, Any], payload: bytes, canonical_url: str | None = None,
    snapshot_root: str | Path | None = None,
) -> tuple[bool, int]:
    """Persist one verified captured response, preserving its exact bytes."""
    if entity.get("id") != qid:
        raise RawWikidataError(f"Parsed Wikidata entity does not match requested QID {qid}.")
    try:
        retained_entity = entity_from_entitydata(json.loads(payload), qid)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RawWikidataError(f"Retained EntityData payload for {qid} is not valid JSON.") from exc
    if retained_entity != entity:
        raise RawWikidataError(f"Retained EntityData payload does not match parsed entity {qid}.")
    capture_url = canonical_url or entitydata_url(qid)
    item = source_object(
        db, source=source, external_id=qid, object_kind="wikibase_item",
        canonical_url=f"{SOURCE_URL}wiki/{qid}",
    )
    source_revision = str(entity.get("lastrevid")) if entity.get("lastrevid") else None
    stored_snapshot, created = snapshot(
        db, item=item, run=run, payload=payload, source_revision=source_revision,
        canonical_url=capture_url, license="CC0 1.0",
        attribution_url=f"{SOURCE_URL}wiki/{qid}", parser_version=ADAPTER_VERSION,
        storage_root=snapshot_root,
    )
    # Replaying an existing exact snapshot can append newly supported source
    # fields while the original source bytes and prior statements stay intact.
    assertions_created = (extract_assertions(db, stored_snapshot.id, entity) if created
                          else extract_english_label(db, stored_snapshot.id, entity))
    return created, assertions_created


def start_ingestion_run(
    db: Session, *, source: DataSource, policy: SourceAccessPolicy,
    requested: int, manifest_uri: str | None,
) -> RawIngestionRun:
    run = RawIngestionRun(
        source_id=source.id, access_policy_id=policy.id,
        adapter_name="wikidata_entity_json", adapter_version=ADAPTER_VERSION,
        manifest_uri=manifest_uri, status="running", records_requested=requested,
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.commit()
    return run


def ingest_entities(
    db: Session,
    entities: dict[str, dict[str, Any]],
    manifest_uri: str | None = None,
    *,
    raw_payloads: dict[str, bytes] | None = None,
    snapshot_root: str | Path | None = None,
) -> dict[str, int]:
    """Persist already-captured entities, requiring their exact source bytes."""
    raw_payloads = raw_payloads or {}
    validated: list[tuple[str, dict[str, Any], bytes]] = []
    for qid, entity in entities.items():
        if not QID.fullmatch(qid):
            raise RawWikidataError(f"Invalid Wikidata QID: {qid}")
        payload = raw_payloads.get(qid)
        if not isinstance(payload, bytes):
            raise RawWikidataError(f"Exact EntityData response bytes are required for {qid}.")
        try:
            retained_entity = entity_from_entitydata(json.loads(payload), qid)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RawWikidataError(f"Retained EntityData payload for {qid} is not valid JSON.") from exc
        if retained_entity != entity:
            raise RawWikidataError(f"Retained EntityData payload does not match parsed entity {qid}.")
        validated.append((qid, entity, payload))

    source: DataSource = source_for_wikidata(db)
    policy = wikidata_entitydata_policy(db, source)
    if policy.decision != "allowed":
        raise RawWikidataError("The registered Wikidata EntityData policy is not approved; refusing to ingest.")
    run = RawIngestionRun(
        source_id=source.id,
        access_policy_id=policy.id,
        adapter_name="wikidata_entity_json",
        adapter_version=ADAPTER_VERSION,
        manifest_uri=manifest_uri,
        status="running",
        records_requested=len(validated),
        started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    stats = {"objects": 0, "snapshots": 0, "source_assertions": 0}
    db.commit()
    processed = 0
    try:
        for qid, entity, payload in validated:
            created, assertions_created = persist_entity_capture(
                db, source=source, run=run, qid=qid, entity=entity,
                payload=payload, snapshot_root=snapshot_root,
            )
            stats["objects"] += 1
            stats["snapshots"] += int(created)
            stats["source_assertions"] += assertions_created
            processed += 1
            run.records_snapshotted = stats["snapshots"]
            db.commit()
        run.status = "complete"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_run = db.get(RawIngestionRun, run.id)
        if failed_run:
            failed_run.status = "failed"
            failed_run.error_summary = f"{type(exc).__name__}: {exc}"[:1000]
            failed_run.records_snapshotted = stats["snapshots"]
            failed_run.records_failed = len(validated) - processed
            failed_run.completed_at = datetime.now(timezone.utc)
            db.commit()
        raise
    return stats


def ingest_selected_qids(db: Session, qids: list[str], manifest_uri: str | None = None) -> dict[str, int]:
    """Verify the registered access decision before the network request."""
    source = source_for_wikidata(db)
    policy = wikidata_entitydata_policy(db, source)
    if policy.decision != "allowed":
        raise RawWikidataError("The registered Wikidata EntityData policy is not approved; refusing to fetch.")
    unique_qids = list(dict.fromkeys(qids))
    if not unique_qids or any(not QID.fullmatch(qid) for qid in unique_qids):
        raise RawWikidataError("A raw Wikidata run requires one or more valid QIDs.")
    settings = get_settings()
    stats = {"objects": 0, "snapshots": 0, "source_assertions": 0}
    with WikidataEntityDataFetcher(
        user_agent=settings.wikidata_user_agent,
        interval_seconds=max(1.0, settings.source_request_interval_seconds),
    ) as fetcher:
        policy = wikidata_entitydata_policy(db, source, robots_sha256=fetcher.robots_sha256)
        if policy.decision != "allowed":
            raise RawWikidataError("The registered Wikidata EntityData policy is not approved; refusing to fetch.")
        run = start_ingestion_run(
            db, source=source, policy=policy, requested=len(unique_qids),
            manifest_uri=manifest_uri,
        )
        processed = 0
        try:
            for qid in unique_qids:
                # Fetch exactly one item, then persist and commit it before the
                # next request. If the process stops, earlier snapshots remain.
                capture = fetcher.fetch(qid)
                created, assertions_created = persist_entity_capture(
                    db, source=source, run=run, qid=qid, entity=capture.entity,
                    payload=capture.payload, canonical_url=capture.canonical_url,
                )
                stats["objects"] += 1
                stats["snapshots"] += int(created)
                stats["source_assertions"] += assertions_created
                processed += 1
                run.records_snapshotted = stats["snapshots"]
                db.commit()
            run.status = "complete"
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            db.rollback()
            failed_run = db.get(RawIngestionRun, run.id)
            if failed_run:
                failed_run.status = "failed"
                failed_run.error_summary = f"{type(exc).__name__}: {exc}"[:1000]
                failed_run.records_snapshotted = stats["snapshots"]
                failed_run.records_failed = len(unique_qids) - processed
                failed_run.completed_at = datetime.now(timezone.utc)
                db.commit()
            raise
    return stats


def main() -> None:
    from app.db import SessionLocal
    from app.migrations import run_migrations

    parser = argparse.ArgumentParser(description="Snapshot selected CC0 Wikidata entities before normalization.")
    parser.add_argument("qids", nargs="*", help="Selected Wikidata QIDs; discovery remains a separate manifest step.")
    parser.add_argument("--manifest", type=Path, help="JSONL entries carrying verified wikidata_id values")
    args = parser.parse_args()
    if bool(args.qids) == bool(args.manifest):
        parser.error("provide QIDs or --manifest, but not both")
    qids = args.qids
    if args.manifest:
        qids = list(dict.fromkeys(
            json.loads(line)["wikidata_id"]
            for line in args.manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ))
    if any(not QID.fullmatch(qid) for qid in qids):
        parser.error("manifest contains an invalid Wikidata ID")
    run_migrations()
    with SessionLocal() as db:
        print(ingest_selected_qids(db, qids,
                                   manifest_uri=str(args.manifest) if args.manifest else None))


if __name__ == "__main__":
    main()
