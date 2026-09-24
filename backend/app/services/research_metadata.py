"""Pure, conservative display policies for operational film assertions."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping


METADATA_PREDICATES = ("release_event", "runtime", "genre", "original_language")
# Identifier translation, not inference from the language of an article.
LANGUAGE_CODES = {"Q1860": "en", "Q8097": "te", "Q1568": "hi", "Q5885": "ta"}
MINUTE_FACTORS = {"Q7727": Decimal(1), "Q11574": Decimal(1) / 60, "Q25235": Decimal(60)}


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


def display_metadata(
    assertions: list[MetadataAssertion], *, genre_labels: Mapping[str, str],
) -> dict[str, Any]:
    admitted = [a for a in assertions if a.review_status in {"resolved", "published"}
                and a.rank != "deprecated" and a.source_url]
    groups = {p: [a for a in admitted if a.predicate == p] for p in METADATA_PREDICATES}
    issues: set[str] = set()
    dates: list[tuple[int, date | None, MetadataAssertion]] = []
    for item in groups["release_event"]:
        value = item.value
        raw = str(value.get("time", ""))
        match = re.fullmatch(r"\+?(\d{4})-(\d{2})-(\d{2})T00:00:00Z", raw)
        precision = value.get("precision")
        if (not match or not isinstance(precision, int) or precision < 9
                or value.get("calendar_model") != "Q1985727"
                or value.get("before") or value.get("after")):
            issues.add("release_value_not_displayable")
            continue
        year, month, day = map(int, match.groups())
        if not 1 <= year <= 9999:
            continue
        try:
            exact = date(year, month, day) if precision >= 11 else None
        except ValueError:
            issues.add("release_value_not_displayable")
            continue
        dates.append((year, exact, item))
    earliest_year = min((row[0] for row in dates), default=None)
    first_year_dates = [row for row in dates if row[0] == earliest_year]
    # A year/month-precision assertion can predate a known day in the same year.
    exact_release = (min(row[1] for row in first_year_dates)
                     if first_year_dates and all(row[1] for row in first_year_dates) else None)
    release_evidence = [row[2] for row in first_year_dates
                        if exact_release is None or row[1] == exact_release]

    runtime_values: set[int] = set()
    runtime_unresolved = False
    for item in groups["runtime"]:
        value = item.value
        try:
            factor = MINUTE_FACTORS.get(value.get("unit"))
            amount = Decimal(str(value.get("amount")))
            minutes = amount * factor if factor is not None else Decimal("NaN")
            if (not minutes.is_finite() or minutes <= 0 or minutes != minutes.to_integral_value()
                    or item.qualifiers
                    or any(value.get(bound) is not None and Decimal(str(value[bound])) != amount
                           for bound in ("lower_bound", "upper_bound"))):
                runtime_unresolved = True
            else:
                runtime_values.add(int(minutes))
        except (InvalidOperation, TypeError, ValueError):
            runtime_unresolved = True
    if runtime_unresolved or len(runtime_values) > 1:
        issues.add("runtime_requires_version_or_value_resolution")
    runtime = next(iter(runtime_values)) if len(runtime_values) == 1 and not runtime_unresolved else None
    genre_ids = sorted({a.value["wikidata_id"] for a in groups["genre"]
                        if isinstance(a.value.get("wikidata_id"), str)})
    if any(qid not in genre_labels for qid in genre_ids):
        issues.add("some_genre_labels_unavailable")
    language_ids = sorted({a.value["wikidata_id"] for a in groups["original_language"]
                           if isinstance(a.value.get("wikidata_id"), str)})
    language_code = (LANGUAGE_CODES.get(language_ids[0], "und") if len(language_ids) == 1
                     else "mul" if language_ids else "und")
    evidence_groups = {**groups, "release_event": release_evidence}
    return {
        "release_date": exact_release.isoformat() if exact_release else None,
        "release_year": earliest_year,
        "release_basis": "earliest_recorded_release" if dates else None,
        "runtime_minutes": runtime,
        "genres": tuple(sorted({genre_labels[qid] for qid in genre_ids if qid in genre_labels})),
        "genre_ids": tuple(genre_ids), "language_code": language_code,
        "original_language_ids": tuple(language_ids), "metadata_issues": tuple(sorted(issues)),
        "metadata_evidence": {field: [
            {"assertion_id": a.assertion_id, "source_url": a.source_url,
             "source_revision": a.source_revision, "review_status": a.review_status}
            for a in sorted(items, key=lambda a: a.assertion_id)
        ] for field, items in evidence_groups.items()},
    }
