"""Pure policy for projecting retained Wikidata statements.

This module knows source vocabulary and value shapes, but nothing about the
database. Unsupported or malformed statements are explicit outcomes rather
than partially published facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping


TargetMode = Literal["entity", "value"]


@dataclass(frozen=True)
class ProjectionRule:
    predicate: str
    target_mode: TargetMode
    target_kind: str | None = None
    reviewed_when_typed: bool = True


@dataclass(frozen=True)
class ProjectionDecision:
    outcome: Literal["project", "unsupported", "invalid"]
    predicate: str | None = None
    object_qid: str | None = None
    object_kind: str | None = None
    value_json: dict[str, Any] | None = None
    review_status: str | None = None
    reason: str | None = None


# This is deliberately an allow-list. Adding a property is a reviewable policy
# change; unknown source fields never leak into the operational fact graph.
SOURCE_PROPERTY_RULES: Mapping[str, ProjectionRule] = MappingProxyType({
    # Creative and performance credits have a semantically fixed person range.
    "P57": ProjectionRule("director", "entity", "person"),
    "P58": ProjectionRule("writer", "entity", "person"),
    "P161": ProjectionRule("cast", "entity", "person"),
    "P162": ProjectionRule("producer", "entity", "person"),
    "P86": ProjectionRule("composer", "entity", "person"),
    "P344": ProjectionRule("cinematographer", "entity", "person"),
    "P1040": ProjectionRule("editor", "entity", "person"),
    "P2554": ProjectionRule("production_designer", "entity", "person"),
    "P2515": ProjectionRule("costume_designer", "entity", "person"),
    "P725": ProjectionRule("voice_actor", "entity", "person"),
    "P1431": ProjectionRule("executive_producer", "entity", "person"),
    "P674": ProjectionRule("character", "entity", "character"),
    # Work targets must be classified before they can become reviewed routes.
    "P155": ProjectionRule("follows", "entity", "unknown_work", False),
    "P156": ProjectionRule("followed_by", "entity", "unknown_work", False),
    "P144": ProjectionRule("based_on", "entity", "unknown_work", False),
    "P179": ProjectionRule("part_of_series", "entity", "unknown_work", False),
    # Structured context remains a typed value until a dedicated entity family
    # and label source are available. These values are facts, not graph edges.
    "P31": ProjectionRule("instance_of", "value"),
    "P136": ProjectionRule("genre", "value"),
    "P364": ProjectionRule("original_language", "value"),
    "P495": ProjectionRule("country_of_origin", "value"),
    "P272": ProjectionRule("production_company", "value"),
    "P750": ProjectionRule("distributor", "value"),
    "P166": ProjectionRule("award_received", "value"),
    "P1411": ProjectionRule("nominated_for", "value"),
    "P444": ProjectionRule("review_score", "value"),
    "P5021": ProjectionRule("assessment", "value"),
    "P915": ProjectionRule("filming_location", "value"),
    "P840": ProjectionRule("narrative_location", "value"),
    "P921": ProjectionRule("main_subject", "value"),
    "P437": ProjectionRule("distribution_format", "value"),
    "P462": ProjectionRule("color", "value"),
    "P577": ProjectionRule("release_event", "value"),
    "P2047": ProjectionRule("runtime", "value"),
    "P2130": ProjectionRule("budget", "value"),
    "P2142": ProjectionRule("box_office", "value"),
    "P1476": ProjectionRule("title", "value"),
    "P345": ProjectionRule("imdb_identifier", "value"),
    "P1258": ProjectionRule("rotten_tomatoes_identifier", "value"),
    "P6127": ProjectionRule("letterboxd_identifier", "value"),
    "P4947": ProjectionRule("tmdb_identifier", "value"),
    "P646": ProjectionRule("freebase_identifier", "value"),
})

REVIEWED_TARGET_KINDS: Mapping[str, frozenset[str]] = MappingProxyType({
    "follows": frozenset({"film", "episode", "series"}),
    "followed_by": frozenset({"film", "episode", "series"}),
    "part_of_series": frozenset({"film", "episode", "series"}),
    "based_on": frozenset({"book", "play", "comic", "film", "series", "game"}),
})


def _qid_from_uri(value: str) -> str:
    return value.rsplit("/", 1)[-1] if value.startswith("http") else value


def _normalized_value(datavalue: dict[str, Any]) -> dict[str, Any] | None:
    value_type = datavalue.get("type")
    value = datavalue.get("value")
    if value_type == "wikibase-entityid" and isinstance(value, dict):
        qid = value.get("id")
        return {"type": "wikibase_entity", "wikidata_id": qid} if isinstance(qid, str) else None
    if value_type == "time" and isinstance(value, dict) and isinstance(value.get("time"), str):
        result: dict[str, Any] = {
            "type": "time",
            "time": value["time"],
            "precision": value.get("precision"),
        }
        if value.get("calendarmodel"):
            result["calendar_model"] = _qid_from_uri(str(value["calendarmodel"]))
        for key in ("before", "after", "timezone"):
            if value.get(key) not in (None, 0):
                result[key] = value[key]
        return result
    if value_type == "quantity" and isinstance(value, dict) and value.get("amount") is not None:
        result = {
            "type": "quantity",
            "amount": str(value["amount"]),
            "unit": _qid_from_uri(str(value.get("unit", "1"))),
        }
        if value.get("lowerBound") is not None:
            result["lower_bound"] = str(value["lowerBound"])
        if value.get("upperBound") is not None:
            result["upper_bound"] = str(value["upperBound"])
        return result
    if value_type == "monolingualtext" and isinstance(value, dict):
        if isinstance(value.get("text"), str) and isinstance(value.get("language"), str):
            return {"type": "monolingual_text", "text": value["text"], "language": value["language"]}
        return None
    if value_type in {"string", "external-id", "url", "commonsMedia"} and isinstance(value, str):
        return {"type": str(value_type), "value": value}
    if value_type == "globecoordinate" and isinstance(value, dict):
        latitude, longitude = value.get("latitude"), value.get("longitude")
        if isinstance(latitude, (int, float)) and isinstance(longitude, (int, float)):
            return {
                "type": "coordinate", "latitude": latitude, "longitude": longitude,
                "precision": value.get("precision"), "globe": _qid_from_uri(str(value.get("globe", ""))),
            }
    return None


def project_wikidata_statement(
    source_property: str | None,
    raw_value: dict[str, Any],
) -> ProjectionDecision:
    """Map one raw Wikidata mainsnak without inventing labels or target types."""
    rule = SOURCE_PROPERTY_RULES.get(source_property or "")
    if not rule:
        return ProjectionDecision("unsupported", reason="source property is not allow-listed")
    if raw_value.get("snaktype") != "value":
        return ProjectionDecision("invalid", reason="statement has no concrete value")
    datavalue = raw_value.get("datavalue")
    if not isinstance(datavalue, dict):
        return ProjectionDecision("invalid", reason="statement datavalue is missing")
    normalized = _normalized_value(datavalue)
    if not normalized:
        return ProjectionDecision("invalid", reason="statement datatype is unsupported or malformed")
    if rule.target_mode == "entity":
        qid = normalized.get("wikidata_id")
        if not isinstance(qid, str) or not qid.startswith("Q") or not qid[1:].isdigit():
            return ProjectionDecision("invalid", reason="entity target has no valid Wikidata identifier")
        return ProjectionDecision(
            "project", predicate=rule.predicate, object_qid=qid,
            object_kind=rule.target_kind,
            review_status="resolved" if rule.reviewed_when_typed else "review_required",
        )
    return ProjectionDecision(
        "project", predicate=rule.predicate, value_json=normalized,
        review_status="resolved",
    )


def review_status_for_target(decision: ProjectionDecision, actual_kind: str) -> str:
    """Publish only target kinds that satisfy the declared predicate range."""
    if decision.object_kind and decision.object_kind != "unknown_work":
        return "resolved" if actual_kind == decision.object_kind else "review_required"
    return (
        "resolved"
        if actual_kind in REVIEWED_TARGET_KINDS.get(decision.predicate or "", frozenset())
        else "review_required"
    )
