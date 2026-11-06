"""Pure, conservative display policies for operational film assertions."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping


METADATA_PREDICATES = ("release_event", "runtime", "genre", "original_language")
# Identifier translation, not inference from the language of an article.
LANGUAGE_CODES = {
    "Q1860": "en", "Q8097": "te", "Q1568": "hi", "Q5885": "ta",
    "Q36236": "ml", "Q33673": "kn", "Q9610": "bn", "Q1571": "mr",
}
MINUTE_FACTORS = {"Q7727": Decimal(1), "Q11574": Decimal(1) / 60, "Q25235": Decimal(60)}


def language_code_for_qids(qids: set[str]) -> str:
    """A single-valued profile must not arbitrarily choose one of several languages."""
    if len(qids) > 1:
        return "mul"
    if not qids:
        return "und"
    return LANGUAGE_CODES.get(next(iter(qids)), "und")


def _minute_value(value: Any, *, unit: str | None) -> int | None:
    factor = MINUTE_FACTORS.get(unit or "")
    if factor is None:
        return None
    try:
        minutes = Decimal(str(value)) * factor
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not minutes.is_finite() or minutes <= 0 or minutes != minutes.to_integral_value():
        return None
    return int(minutes)


def _runtime_scope(qualifiers: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Retain typed qualifier property IDs and entity IDs for display."""
    scope = []
    for property_id, statements in sorted(qualifiers.items()):
        if not isinstance(property_id, str) or not isinstance(statements, list):
            continue
        entity_ids = sorted({
            statement["datavalue"]["value"]["id"]
            for statement in statements
            if isinstance(statement, dict)
            and isinstance(statement.get("datavalue"), dict)
            and isinstance(statement["datavalue"].get("value"), dict)
            and isinstance(statement["datavalue"]["value"].get("id"), str)
        })
        if entity_ids:
            scope.append({"property_id": property_id, "entity_ids": entity_ids})
    return scope


@dataclass(frozen=True)
class MetadataAssertion:
    assertion_id: str
    predicate: str
    value: dict[str, Any]
    qualifiers: dict[str, Any]
    review_status: str
    rank: str | None
    source_url: str
    source_revision: str | None
    source_name: str | None = None
    source_rights_status: str | None = None
    source_license: str | None = None


def display_metadata(
    assertions: list[MetadataAssertion], *, genre_labels: Mapping[str, str],
) -> dict[str, Any]:
    admitted = [a for a in assertions if a.review_status in {"resolved", "published"}
                and a.rank != "deprecated" and a.source_url]
    groups = {p: [a for a in admitted if a.predicate == p] for p in METADATA_PREDICATES}
    issues: set[str] = set()
    dates: list[tuple[int, date | None, MetadataAssertion]] = []
    release_events: list[dict[str, Any]] = []
    for item in groups["release_event"]:
        value = item.value
        raw = str(value.get("time", ""))
        match = re.fullmatch(r"\+?(\d{4})-(\d{2})-(\d{2})T00:00:00Z", raw)
        precision = value.get("precision")
        if (not match or not isinstance(precision, int) or precision not in {9, 10, 11}
                or value.get("calendar_model") != "Q1985727"
                or value.get("before") or value.get("after")):
            issues.add("release_value_not_displayable")
            continue
        year, month, day = map(int, match.groups())
        if not 1 <= year <= 9999:
            continue
        try:
            exact = date(year, month, day) if precision == 11 else None
        except ValueError:
            issues.add("release_value_not_displayable")
            continue
        dates.append((year, exact, item))
        place_ids = sorted({
            place["datavalue"]["value"]["id"]
            for place in item.qualifiers.get("P291", [])
            if isinstance(place, dict)
            and isinstance(place.get("datavalue"), dict)
            and isinstance(place["datavalue"].get("value"), dict)
            and isinstance(place["datavalue"]["value"].get("id"), str)
        })
        release_events.append({
            "assertion_id": item.assertion_id,
            "year": year,
            "date": exact.isoformat() if exact else None,
            "precision": precision,
            "place_ids": place_ids,
            "source_url": item.source_url,
            "source_revision": item.source_revision,
            "review_status": item.review_status,
            "source_name": item.source_name,
            "source_rights_status": item.source_rights_status,
            "source_license": item.source_license,
        })
    earliest_year = min((row[0] for row in dates), default=None)
    first_year_dates = [row for row in dates if row[0] == earliest_year]
    # A year/month-precision assertion can predate a known day in the same year.
    exact_release = (min(row[1] for row in first_year_dates)
                     if first_year_dates and all(row[1] for row in first_year_dates) else None)
    release_evidence = [row[2] for row in first_year_dates
                        if exact_release is None or row[1] == exact_release]

    runtime_values: set[int] = set()
    runtime_unresolved = False
    runtime_options: list[dict[str, Any]] = []
    for item in groups["runtime"]:
        value = item.value
        unit = value.get("unit")
        minutes = _minute_value(value.get("amount"), unit=unit)
        lower = (_minute_value(value.get("lower_bound"), unit=unit)
                 if value.get("lower_bound") is not None else None)
        upper = (_minute_value(value.get("upper_bound"), unit=unit)
                 if value.get("upper_bound") is not None else None)
        if minutes is None:
            runtime_unresolved = True
            continue
        scope = _runtime_scope(item.qualifiers)
        runtime_options.append({
            "assertion_id": item.assertion_id,
            "minutes": minutes,
            "lower_bound_minutes": lower,
            "upper_bound_minutes": upper,
            "scope": scope,
            "source_url": item.source_url,
            "source_revision": item.source_revision,
            "review_status": item.review_status,
            "source_name": item.source_name,
            "source_rights_status": item.source_rights_status,
            "source_license": item.source_license,
        })
        malformed_bound = (
            (value.get("lower_bound") is not None and lower is None)
            or (value.get("upper_bound") is not None and upper is None)
        )
        if item.qualifiers or malformed_bound or lower not in (None, minutes) or upper not in (None, minutes):
            runtime_unresolved = True
        else:
            runtime_values.add(minutes)
    if runtime_unresolved or len(runtime_values) > 1:
        issues.add("runtime_requires_version_or_value_resolution")
    runtime = next(iter(runtime_values)) if len(runtime_values) == 1 and not runtime_unresolved else None
    genre_ids = sorted({a.value["wikidata_id"] for a in groups["genre"]
                        if isinstance(a.value.get("wikidata_id"), str)})
    if any(qid not in genre_labels for qid in genre_ids):
        issues.add("some_genre_labels_unavailable")
    language_ids = sorted({a.value["wikidata_id"] for a in groups["original_language"]
                           if isinstance(a.value.get("wikidata_id"), str)})
    language_code = language_code_for_qids(set(language_ids))
    evidence_groups = {**groups, "release_event": release_evidence}
    release_events.sort(key=lambda event: (
        event["year"], event["date"] or "", event["place_ids"], event["assertion_id"],
    ))
    runtime_options.sort(key=lambda option: (
        option["minutes"],
        tuple((scope["property_id"], tuple(scope["entity_ids"])) for scope in option["scope"]),
        option["source_name"] or "", option["assertion_id"],
    ))
    return {
        "release_date": exact_release.isoformat() if exact_release else None,
        "release_year": earliest_year,
        "release_basis": "earliest_recorded_release" if dates else None,
        "runtime_minutes": runtime,
        "runtime_options": tuple(runtime_options),
        "genres": tuple(sorted({genre_labels[qid] for qid in genre_ids if qid in genre_labels})),
        "genre_ids": tuple(genre_ids), "language_code": language_code,
        "original_language_ids": tuple(language_ids), "metadata_issues": tuple(sorted(issues)),
        "release_events": tuple(release_events),
        "metadata_evidence": {field: [
            {"assertion_id": a.assertion_id, "source_url": a.source_url,
             "source_revision": a.source_revision, "review_status": a.review_status,
             "source_name": a.source_name, "source_rights_status": a.source_rights_status,
             "source_license": a.source_license}
            for a in sorted(items, key=lambda a: a.assertion_id)
        ] for field, items in evidence_groups.items()},
    }
