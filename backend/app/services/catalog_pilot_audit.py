"""Offline integrity and coverage audit for captured catalog-pilot bundles."""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from app.services.catalog_pilot_capture import CatalogPilotCaptureError
from app.services.wikidata_raw import entity_from_entitydata
from app.services.wikidata_selection_resolution import is_film, is_film_in_year, title_score
from app.services.wikipedia_article_html import PARSER_VERSION, parse_article_html


class CatalogPilotAuditError(RuntimeError):
    """The local capture bundle is incomplete or does not match its hashes."""


WIKIDATA_METADATA_PROPERTIES = {
    "release_date": "P577",
    "runtime": "P2047",
    "country": "P495",
    "original_language": "P364",
    "genre": "P136",
    "director": "P57",
    "cast": "P161",
    "screenwriter": "P58",
    "producer": "P162",
    "cinematography": "P344",
    "editing": "P1040",
    "music": "P86",
    "production_company": "P272",
}


def _value_statements(claims: dict[str, Any], property_id: str) -> list[dict[str, Any]]:
    rows = claims.get(property_id, [])
    if not isinstance(rows, list):
        return []
    return [statement for statement in rows
            if isinstance(statement, dict)
            if statement.get("rank") != "deprecated"
            and statement.get("mainsnak", {}).get("snaktype", "value") == "value"
            and "datavalue" in statement.get("mainsnak", {})]


def structured_metadata_coverage(claims: dict[str, Any]) -> dict[str, Any]:
    """Count value-bearing Wikidata statements without treating them as verified facts."""
    counts = {
        field: len(_value_statements(claims, property_id))
        for field, property_id in WIKIDATA_METADATA_PROPERTIES.items()
    }
    cast = _value_statements(claims, "P161")
    with_character_entity = sum(
        bool(statement.get("qualifiers", {}).get("P453")) for statement in cast
    )
    with_character_name = sum(
        bool(statement.get("qualifiers", {}).get("P4633")) for statement in cast
    )
    with_character = sum(
        bool({"P453", "P4633"} & statement.get("qualifiers", {}).keys())
        for statement in cast
    )
    release_dates = _value_statements(claims, "P577")
    precision_counts: Counter[str] = Counter()
    for statement in release_dates:
        value = statement.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        if isinstance(value, dict) and value.get("precision") is not None:
            precision_counts[str(value["precision"])] += 1
    return {
        "value_statement_counts": counts,
        "release_date_precision_counts": dict(sorted(precision_counts.items())),
        "release_dates_with_territory": sum(
            bool(statement.get("qualifiers", {}).get("P291")) for statement in release_dates
        ),
        "release_dates_with_references": sum(bool(statement.get("references")) for statement in release_dates),
        "runtime_values_with_references": sum(
            bool(statement.get("references")) for statement in _value_statements(claims, "P2047")
        ),
        "cast_character_entity_qualifiers": with_character_entity,
        "cast_character_name_qualifiers": with_character_name,
        "cast_with_character_qualifier": with_character,
        "cast_without_character_qualifier": len(cast) - with_character,
    }


def section_categories(section_counts: dict[str, int]) -> dict[str, int]:
    categories = {"plot": 0, "production": 0, "reception": 0, "themes_analysis": 0, "legacy": 0}
    for section, count in section_counts.items():
        normalized = section.casefold()
        # Match the shared passage-coverage policy: many well-structured film
        # articles call their narrative section "Synopsis" or "Story".
        if any(label in normalized for label in ("plot", "synopsis", "story")):
            categories["plot"] += count
        if "production" in normalized or "casting" in normalized:
            categories["production"] += count
        if "reception" in normalized or "critical" in normalized or "accolade" in normalized or "award" in normalized:
            categories["reception"] += count
        if "theme" in normalized or "analysis" in normalized:
            categories["themes_analysis"] += count
        if "legacy" in normalized or "influence" in normalized or "cultural" in normalized:
            categories["legacy"] += count
    return categories


def missing_content_categories(categories: dict[str, int]) -> list[str]:
    """Report absent article sections without treating them as capture corruption."""
    return [name for name in ("plot", "production") if not categories.get(name)]


def _content_coverage(film_rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Summarize source section availability separately from capture integrity."""
    return {
        category: {
            "films_with_section": sum(bool(film["categories"][category]) for film in film_rows),
            "films_missing_section": sum(not film["categories"][category] for film in film_rows),
        }
        for category in ("plot", "production", "reception", "themes_analysis", "legacy")
    }


def audit_capture_bundle(output_dir: Path) -> dict[str, Any]:
    manifest_path = output_dir / "capture-manifest.json"
    if not manifest_path.is_file():
        raise CatalogPilotAuditError(f"Missing capture manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "cinegraph.catalog-pilot-capture/v1":
        raise CatalogPilotAuditError("Unsupported capture manifest schema.")
    parser_generation = PARSER_VERSION.rsplit("-v", 1)[-1]
    extraction_manifest_path = output_dir / f"extraction-manifest-{parser_generation}.json"
    extraction_rows: dict[str, dict[str, Any]] = {}
    if extraction_manifest_path.is_file():
        extraction_manifest = json.loads(extraction_manifest_path.read_text(encoding="utf-8"))
        if (extraction_manifest.get("schema") != "cinegraph.catalog-pilot-extraction/v1"
                or extraction_manifest.get("parser_version") != PARSER_VERSION
                or extraction_manifest.get("selection_sha256") != manifest.get("selection_sha256")):
            raise CatalogPilotAuditError("Versioned extraction manifest does not match capture/parser selection.")
        extraction_rows = {film["qid"]: film for film in extraction_manifest.get("films", [])}
    film_rows: list[dict[str, Any]] = []
    passage_hashes: Counter[str] = Counter()
    errors: list[str] = []
    total_capture_bytes = 0
    total_passages = 0
    total_cited_passages = 0
    short_passages = 0
    long_passages = 0
    passage_length_flags: list[dict[str, Any]] = []
    wikidata_field_films: Counter[str] = Counter()
    wikidata_field_statements: Counter[str] = Counter()
    release_date_precision: Counter[str] = Counter()
    release_dates_with_territory = 0
    release_dates_with_references = 0
    runtime_values_with_references = 0
    cast_total = cast_with_character = cast_character_entities = cast_character_names = 0
    content_gaps: list[dict[str, Any]] = []

    for film in manifest.get("films", []):
        title, qid = film.get("title"), film.get("qid")
        try:
            wiki_path = output_dir / film["wikidata_snapshot_path"]
            wiki_bytes = wiki_path.read_bytes()
            wiki_hash = sha256(wiki_bytes).hexdigest()
            if wiki_hash != film.get("wikidata_sha256"):
                raise CatalogPilotAuditError(f"{qid}: Wikidata snapshot SHA-256 mismatch.")
            entity = entity_from_entitydata(json.loads(wiki_bytes), qid)
            if entity.get("lastrevid") != film.get("wikidata_revision"):
                raise CatalogPilotAuditError(f"{qid}: Wikidata revision disagrees with manifest.")
            if not title_score(entity, title) or not is_film(entity) or not is_film_in_year(entity, film["year"]):
                raise CatalogPilotAuditError(f"{qid}: title/year identity no longer validates against capture.")
            if entity.get("sitelinks", {}).get("enwiki", {}).get("title") != film.get("enwiki_title"):
                raise CatalogPilotAuditError(f"{qid}: enwiki sitelink disagrees with retained entity.")
            metadata_coverage = structured_metadata_coverage(entity.get("claims", {}))
            for field, count in metadata_coverage["value_statement_counts"].items():
                wikidata_field_statements[field] += count
                wikidata_field_films[field] += bool(count)
            release_date_precision.update(metadata_coverage["release_date_precision_counts"])
            release_dates_with_territory += metadata_coverage["release_dates_with_territory"]
            release_dates_with_references += metadata_coverage["release_dates_with_references"]
            runtime_values_with_references += metadata_coverage["runtime_values_with_references"]
            cast_total += metadata_coverage["value_statement_counts"]["cast"]
            cast_with_character += metadata_coverage["cast_with_character_qualifier"]
            cast_character_entities += metadata_coverage["cast_character_entity_qualifiers"]
            cast_character_names += metadata_coverage["cast_character_name_qualifiers"]

            page_path = output_dir / film["wikipedia_snapshot_path"]
            page_bytes = page_path.read_bytes()
            page_hash = sha256(page_bytes).hexdigest()
            if page_hash != film.get("wikipedia_sha256"):
                raise CatalogPilotAuditError(f"{qid}: Wikipedia HTML SHA-256 mismatch.")
            document = parse_article_html(
                page_bytes, canonical_url=film["wikipedia_capture_url"], expected_qid=qid,
            )
            if document.metadata.revision_id != film.get("wikipedia_revision"):
                raise CatalogPilotAuditError(f"{qid}: Wikipedia revision disagrees with manifest.")
            if document.metadata.title != film.get("wikipedia_title_resolved"):
                raise CatalogPilotAuditError(f"{qid}: resolved page title disagrees with manifest.")

            extraction = extraction_rows.get(qid)
            if extraction:
                if (extraction.get("source_snapshot_sha256") != page_hash
                        or extraction.get("source_revision") != document.metadata.revision_id):
                    raise CatalogPilotAuditError(f"{qid}: versioned extraction is bound to another source revision.")
                relative_derivative_path = extraction["passage_derivative_path"]
                expected_derivative_hash = extraction.get("passage_derivative_sha256")
            else:
                relative_derivative_path = film["passage_derivative_path"]
                expected_derivative_hash = film["passage_derivative_sha256"]
            derivative_path = output_dir / relative_derivative_path
            derivative_bytes = derivative_path.read_bytes()
            derivative_hash = sha256(derivative_bytes).hexdigest()
            if derivative_hash != expected_derivative_hash:
                raise CatalogPilotAuditError(f"{qid}: passage derivative SHA-256 mismatch.")
            derivative = json.loads(derivative_bytes)
            passages = derivative.get("passages", [])
            if (derivative.get("source_snapshot_sha256") != page_hash
                    or derivative.get("source_revision") != document.metadata.revision_id
                    or derivative.get("parser_version") != document.parser_version
                    or len(passages) != len(document.passages)):
                raise CatalogPilotAuditError(f"{qid}: derivative is not bound to the captured article/parser revision.")
            section_counts: Counter[str] = Counter()
            citation_count = 0
            char_lengths: list[int] = []
            film_length_flags: list[dict[str, Any]] = []
            for passage in passages:
                content = passage.get("content", "")
                content_hash = sha256(content.encode("utf-8")).hexdigest()
                if content_hash != passage.get("content_sha256") or not content.strip():
                    raise CatalogPilotAuditError(f"{qid}: passage content is empty or its content hash is invalid.")
            # Independently recompute the derivative rows in parser order.
            for serialized, parsed in zip(passages, document.passages, strict=True):
                if (serialized.get("section_locator"), serialized.get("section_title"),
                        serialized.get("ordinal"), serialized.get("content"),
                        tuple(serialized.get("citation_markers", [])),
                        tuple((item["marker_id"], item["paragraph_index"], item["char_offset"])
                              for item in serialized.get("citation_positions", []))) != (
                    parsed.section_locator, parsed.section_title, parsed.ordinal,
                    parsed.content, parsed.citation_markers, parsed.citation_positions,
                ):
                    raise CatalogPilotAuditError(f"{qid}: extracted passage differs from deterministic parser output.")
                section_counts[parsed.section_title] += 1
                citation_count += bool(parsed.citation_markers)
                char_lengths.append(len(parsed.content))
                passage_hashes[parsed.content_hash] += 1
                length = len(parsed.content)
                if length < 80 or length > 2500:
                    flag = {
                        "title": title,
                        "year": film["year"],
                        "qid": qid,
                        "section_locator": parsed.section_locator,
                        "section_title": parsed.section_title,
                        "ordinal": parsed.ordinal,
                        "character_count": length,
                        "content_sha256": parsed.content_hash,
                        "kind": "short" if length < 80 else "long",
                    }
                    film_length_flags.append(flag)
                    passage_length_flags.append(flag)
            categories = section_categories(dict(section_counts))
            missing_categories = missing_content_categories(categories)
            if missing_categories:
                content_gaps.append({"title": title, "qid": qid, "missing_categories": missing_categories})
            total_capture_bytes += len(wiki_bytes) + len(page_bytes)
            total_passages += len(passages)
            total_cited_passages += citation_count
            short_passages += sum(length < 80 for length in char_lengths)
            long_passages += sum(length > 2500 for length in char_lengths)
            film_rows.append({
                "title": title,
                "year": film["year"],
                "qid": qid,
                "wikidata_revision": entity["lastrevid"],
                "wikipedia_revision": document.metadata.revision_id,
                "wikipedia_title": document.metadata.title,
                "wikidata_bytes": len(wiki_bytes),
                "wikipedia_bytes": len(page_bytes),
                "passage_count": len(passages),
                "section_count": len(section_counts),
                "cited_passage_count": citation_count,
                "wikidata_metadata": metadata_coverage,
                "categories": categories,
                "missing_content_categories": missing_categories,
                "sections": dict(sorted(section_counts.items())),
                "passage_length_flags": film_length_flags,
            })
        except (CatalogPilotAuditError, CatalogPilotCaptureError, KeyError, OSError, ValueError, TypeError) as exc:
            errors.append(f"{title} ({qid}): {type(exc).__name__}: {exc}")

    duplicate_passages = sum(count - 1 for count in passage_hashes.values() if count > 1)
    requested = len(manifest.get("films", []))
    return {
        "schema": "cinegraph.catalog-pilot-audit/v3",
        "selection_sha256": manifest.get("selection_sha256"),
        "run_status": manifest.get("run_status"),
        "requested_films": requested,
        "audited_films": len(film_rows),
        "identity_and_capture_pass": not errors and len(film_rows) == requested,
        "content_coverage": _content_coverage(film_rows),
        "content_gaps": content_gaps,
        "wikidata_robots_sha256": manifest.get("wikidata_robots_sha256"),
        "wikipedia_robots_sha256": manifest.get("wikipedia_robots_sha256"),
        "total_raw_capture_bytes": total_capture_bytes,
        "total_passages": total_passages,
        "unique_passage_texts": len(passage_hashes),
        "exact_duplicate_passages": duplicate_passages,
        "passages_with_citation_markers": total_cited_passages,
        "passage_citation_marker_coverage": round(total_cited_passages / total_passages, 4) if total_passages else 0,
        "passages_under_80_chars": short_passages,
        "passages_over_2500_chars": long_passages,
        "passage_length_flags": passage_length_flags,
        "wikidata_metadata_coverage": {
            field: {
                "films_with_value": wikidata_field_films[field],
                "value_statements": wikidata_field_statements[field],
            }
            for field in WIKIDATA_METADATA_PROPERTIES
        },
        "release_date_precision_counts": dict(sorted(release_date_precision.items())),
        "release_dates_with_territory": release_dates_with_territory,
        "release_dates_with_references": release_dates_with_references,
        "runtime_values_with_references": runtime_values_with_references,
        "cast_credit_statements": cast_total,
        "cast_credits_with_character_qualifier": cast_with_character,
        "cast_credits_with_character_entity_qualifier": cast_character_entities,
        "cast_credits_with_character_name_qualifier": cast_character_names,
        "cast_credits_without_character_qualifier": cast_total - cast_with_character,
        "failures": errors,
        "films": film_rows,
        "limitations": [
            "This verifies capture integrity, identity checks and deterministic extraction, not semantic correctness or legal advice.",
            "Citation marker presence does not prove a reference link, source support, or reuse permission; consult the separate citation-target audit.",
            "A passage count does not measure completeness, relevance, or writer usefulness.",
            "No source data were inserted into the working catalog or embedding index.",
        ],
    }


def render_audit_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Catalog pilot source-capture audit",
        "",
        "Source identity, snapshot hashes, and deterministic extraction: "
        + ("PASS" if report["identity_and_capture_pass"] else "FAIL"),
        "",
        f"Selection SHA-256: `{report['selection_sha256']}`",
        f"Films audited: {report['audited_films']} / {report['requested_films']}",
        f"Source bytes (Wikidata JSON + Wikipedia HTML): {report['total_raw_capture_bytes']:,}",
        f"Extracted passages: {report['total_passages']:,} ({report['unique_passage_texts']:,} unique; {report['exact_duplicate_passages']} exact duplicates)",
        f"Passages with source citation markers: {report['passages_with_citation_markers']:,} ({report['passage_citation_marker_coverage']:.1%})",
        f"Passages under 80 characters / over 2,500 characters: {report['passages_under_80_chars']} / {report['passages_over_2500_chars']}",
        "Length flags identify source section/ordinal and content hash; they do not include passage text or imply extraction failure.",
        "",
        "| Film | QID | Wikidata rev. | Wikipedia rev. | Bytes (JSON + HTML) | Passages | Sections | Plot | Production | Reception | Themes/analysis | Legacy |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for film in report["films"]:
        categories = film["categories"]
        lines.append(
            f"| {film['title']} ({film['year']}) | `{film['qid']}` | {film['wikidata_revision']} | "
            f"{film['wikipedia_revision']} | {film['wikidata_bytes'] + film['wikipedia_bytes']:,} | "
            f"{film['passage_count']} | {film['section_count']} | {categories['plot']} | "
            f"{categories['production']} | {categories['reception']} | {categories['themes_analysis']} | {categories['legacy']} |"
        )
    length_flags = report.get("passage_length_flags", [])
    if length_flags:
        lines.extend([
            "",
            "## Passage length review flags",
            "",
            "These are inspection cues only. Short sections can be valid metadata or quotations; long sections may need downstream chunking, but are not dropped here.",
            "",
            "| Film | QID | Section | Ordinal | Characters | Flag | Content SHA-256 |",
            "| --- | --- | --- | ---: | ---: | --- | --- |",
        ])
        for flag in length_flags:
            lines.append(
                f"| {flag['title']} ({flag['year']}) | `{flag['qid']}` | {flag['section_title']} "
                f"(`{flag['section_locator']}`) | {flag['ordinal']} | {flag['character_count']} | "
                f"{flag['kind']} | `{flag['content_sha256']}` |"
            )
    coverage = report["content_coverage"]
    lines.extend([
        "",
        "## Article section availability (not an integrity gate)",
        "",
        "| Section category | Films with section | Films missing section |",
        "| --- | ---: | ---: |",
    ])
    for category, values in coverage.items():
        lines.append(f"| {category.replace('_', ' ')} | {values['films_with_section']} | {values['films_missing_section']} |")
    if report["content_gaps"]:
        lines.extend(["", "Films with missing plot/production sections:", ""])
        for gap in report["content_gaps"]:
            missing = ", ".join(gap["missing_categories"])
            lines.append(f"- {gap['title']} (`{gap['qid']}`): {missing}")
    lines.extend([
        "",
        "## Structured Wikidata field coverage",
        "",
        "Counts below describe value-bearing statements in the retained CC0 EntityData snapshots; they do not verify correctness, completeness, or operational database/API projection.",
        "",
        "| Field | Films with values | Value statements |",
        "| --- | ---: | ---: |",
    ])
    for field, coverage in report["wikidata_metadata_coverage"].items():
        lines.append(f"| {field.replace('_', ' ')} | {coverage['films_with_value']} | {coverage['value_statements']} |")
    lines.extend([
        "",
        f"Release-date statements by Wikidata precision code: `{report['release_date_precision_counts']}`; "
        f"territory-qualified: {report['release_dates_with_territory']}; source-referenced: {report['release_dates_with_references']}",
        f"Cast statements: {report['cast_credit_statements']}; with a character entity qualifier (P453): "
        f"{report['cast_credits_with_character_entity_qualifier']}; with a character-name qualifier (P4633): "
        f"{report['cast_credits_with_character_name_qualifier']}; with either: "
        f"{report['cast_credits_with_character_qualifier']}; with neither: "
        f"{report['cast_credits_without_character_qualifier']}.",
        "These role qualifiers are not necessarily visible in the current application projection.",
        "",
        "## Source policy and interpretation",
        "",
    ])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend([
        "- Wikidata robots SHA-256: `" + str(report.get("wikidata_robots_sha256")) + "`",
        "- English Wikipedia robots SHA-256: `" + str(report.get("wikipedia_robots_sha256")) + "`",
        "- Wikidata structured payloads are CC0; Wikipedia article prose is CC BY-SA 4.0 and requires attribution/share-alike compliance for redistribution.",
        "- Raw snapshots and passage derivatives remain in ignored local evaluation storage; this summary contains no article prose.",
    ])
    if report["failures"]:
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in report["failures"])
    return "\n".join(lines) + "\n"
