"""Resolve retained Wikipedia passage citation markers to article references.

This is an offline provenance audit. It records reference IDs and outbound
source URLs only; it does not copy reference prose or declare the linked
sources licensed for reuse.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.services.wikipedia_article_html import PARSER_VERSION


class _CitationReferenceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.marker_id: str | None = None
        self.reference_id: str | None = None
        self.marker_to_reference: dict[str, list[str]] = {}
        self.reference_urls: dict[str, list[str]] = {}
        self.reference_entries: set[str] = set()
        self._stack: list[tuple[str, str | None, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        previous_marker, previous_reference = self.marker_id, self.reference_id
        if tag == "sup" and ("reference" in classes or "mw-ref" in classes):
            candidate = values.get("id")
            self.marker_id = candidate if candidate and candidate.startswith("cite_ref-") else None
        if tag == "li":
            candidate = values.get("id")
            self.reference_id = candidate if candidate and candidate.startswith("cite_note-") else None
            if self.reference_id:
                self.reference_entries.add(self.reference_id)
        if tag == "a" and values.get("href"):
            href = str(values["href"])
            if self.marker_id and href.startswith("#cite_note-"):
                target = href.removeprefix("#")
                references = self.marker_to_reference.setdefault(self.marker_id, [])
                if target not in references:
                    references.append(target)
            if self.reference_id:
                absolute = urljoin("https://en.wikipedia.org/", href)
                parsed = urlsplit(absolute)
                host = (parsed.hostname or "").casefold()
                if parsed.scheme in {"http", "https"} and host and host not in {
                    "en.wikipedia.org", "www.wikipedia.org", "wikipedia.org",
                }:
                    urls = self.reference_urls.setdefault(self.reference_id, [])
                    if absolute not in urls:
                        urls.append(absolute)
        self._stack.append((tag, previous_marker, previous_reference))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            open_tag, prior_marker, prior_reference = self._stack[index]
            if open_tag != tag:
                continue
            del self._stack[index:]
            self.marker_id, self.reference_id = prior_marker, prior_reference
            break


def citation_reference_index(payload: bytes) -> dict[str, dict[str, Any]]:
    """Return marker -> cited reference IDs and outbound URLs from retained HTML."""
    parser = _CitationReferenceParser()
    parser.feed(payload.decode("utf-8"))
    parser.close()
    results: dict[str, dict[str, Any]] = {}
    for marker, reference_ids in sorted(parser.marker_to_reference.items()):
        missing = [reference_id for reference_id in reference_ids
                   if not parser.reference_urls.get(reference_id)]
        urls = sorted({url for reference_id in reference_ids
                       for url in parser.reference_urls.get(reference_id, [])})
        results[marker] = {
            "reference_ids": reference_ids,
            "reference_entry_present": any(reference_id in parser.reference_entries
                                             for reference_id in reference_ids),
            "reference_ids_without_external_url": missing,
            "external_urls": urls,
        }
    return results


def audit_catalog_citations(bundle: Path) -> dict[str, Any]:
    """Audit marker resolution for an already captured pilot bundle; no network."""
    manifest = json.loads((bundle / "capture-manifest.json").read_text(encoding="utf-8"))
    version = PARSER_VERSION.rsplit("-v", 1)[-1]
    extraction_manifest_path = bundle / f"extraction-manifest-{version}.json"
    extraction_rows: dict[str, dict[str, Any]] = {}
    if extraction_manifest_path.is_file():
        extraction_manifest = json.loads(extraction_manifest_path.read_text(encoding="utf-8"))
        if extraction_manifest.get("parser_version") != PARSER_VERSION:
            raise ValueError("Extraction manifest parser version does not match citation audit version.")
        extraction_rows = {film["qid"]: film for film in extraction_manifest.get("films", [])}
        if set(extraction_rows) != {film["qid"] for film in manifest.get("films", [])}:
            raise ValueError("Versioned extraction manifest does not cover the full capture selection.")
    films: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    passage_rows: list[dict[str, Any]] = []
    for film in manifest.get("films", []):
        page = (bundle / film["wikipedia_snapshot_path"]).read_bytes()
        extraction = extraction_rows.get(film["qid"])
        if extraction:
            if (extraction.get("source_snapshot_sha256") != film.get("wikipedia_sha256")
                    or extraction.get("source_revision") != film.get("wikipedia_revision")):
                raise ValueError(f"Extraction manifest is bound to a different article revision for {film['qid']}.")
            derivative_path = extraction["passage_derivative_path"]
            if extraction.get("parser_version") != PARSER_VERSION:
                raise ValueError(f"Extraction parser version mismatch for {film['qid']}.")
        else:
            derivative_path = film["passage_derivative_path"]
        derivative_bytes = (bundle / derivative_path).read_bytes()
        if extraction and sha256(derivative_bytes).hexdigest() != extraction.get("passage_derivative_sha256"):
            raise ValueError(f"Passage derivative hash mismatch for {film['qid']}.")
        derivative = json.loads(derivative_bytes)
        reference_index = citation_reference_index(page)
        marker_occurrences = 0
        reference_list_marker_occurrences = 0
        external_url_marker_occurrences = 0
        markers_without_reference_entry = 0
        markers_without_external_url = 0
        cited_passages = 0
        fully_reference_resolved_passages = 0
        fully_external_url_linked_passages = 0
        for passage in derivative.get("passages", []):
            positions = passage.get("citation_positions", [])
            if set(item.get("marker_id") for item in positions) != set(passage.get("citation_markers", [])):
                raise ValueError(f"Citation marker positions are incomplete for {film['qid']} passage {passage.get('ordinal')}.")
            paragraphs = passage.get("content", "").split("\n\n")
            paragraph_starts = []
            cursor = 0
            for paragraph in paragraphs:
                paragraph_starts.append(cursor)
                cursor += len(paragraph) + 2
            for position in positions:
                paragraph_index = position.get("paragraph_index")
                char_offset = position.get("char_offset")
                if (not isinstance(paragraph_index, int) or not 0 <= paragraph_index < len(paragraphs)
                        or not isinstance(char_offset, int)
                        or not paragraph_starts[paragraph_index] <= char_offset
                        <= paragraph_starts[paragraph_index] + len(paragraphs[paragraph_index])):
                    raise ValueError(f"Citation marker offset is out of passage bounds for {film['qid']}.")
            markers = [item["marker_id"] for item in positions]
            if markers:
                cited_passages += 1
                marker_occurrences += len(markers)
                resolutions = [reference_index.get(marker) for marker in markers]
                reference_list_resolved = [item for item in resolutions
                                           if item and item["reference_entry_present"]]
                external_url_resolved = [item for item in resolutions if item and item["external_urls"]]
                reference_list_marker_occurrences += len(reference_list_resolved)
                external_url_marker_occurrences += len(external_url_resolved)
                markers_without_reference_entry += len(markers) - len(reference_list_resolved)
                markers_without_external_url += len(markers) - len(external_url_resolved)
                if len(reference_list_resolved) == len(markers):
                    fully_reference_resolved_passages += 1
                if len(external_url_resolved) == len(markers):
                    fully_external_url_linked_passages += 1
                marker_details = []
                for position in positions:
                    marker = position["marker_id"]
                    marker_details.append({
                        "marker_id": marker,
                        "paragraph_index": position["paragraph_index"],
                        "char_offset": position["char_offset"],
                        **reference_index.get(marker, {
                            "reference_ids": [], "reference_entry_present": False,
                            "reference_ids_without_external_url": [], "external_urls": [],
                        }),
                    })
                passage_rows.append({
                    "qid": film["qid"],
                    "title": film["title"],
                    "section_locator": passage["section_locator"],
                    "ordinal": passage["ordinal"],
                    "markers": marker_details,
                })
        totals.update({
            "passages": len(derivative.get("passages", [])),
            "cited_passages": cited_passages,
            "fully_reference_resolved_passages": fully_reference_resolved_passages,
            "fully_external_url_linked_passages": fully_external_url_linked_passages,
            "marker_occurrences": marker_occurrences,
            "reference_list_marker_occurrences": reference_list_marker_occurrences,
            "external_url_marker_occurrences": external_url_marker_occurrences,
            "markers_without_reference_entry": markers_without_reference_entry,
            "markers_without_external_url": markers_without_external_url,
        })
        films.append({
            "qid": film["qid"],
            "title": film["title"],
            "passages": len(derivative.get("passages", [])),
            "cited_passages": cited_passages,
            "fully_reference_resolved_passages": fully_reference_resolved_passages,
            "fully_external_url_linked_passages": fully_external_url_linked_passages,
            "marker_occurrences": marker_occurrences,
            "reference_list_marker_occurrences": reference_list_marker_occurrences,
            "external_url_marker_occurrences": external_url_marker_occurrences,
            "markers_without_reference_entry": markers_without_reference_entry,
            "markers_without_external_url": markers_without_external_url,
            "distinct_markers": len(reference_index),
        })
    totals["films"] = len(films)
    totals["passages_without_citations"] = totals["passages"] - totals["cited_passages"]
    return {
        "schema": "cinegraph.catalog-citation-audit/v1",
        "selection_sha256": manifest.get("selection_sha256"),
        "source_scope": "retained English Wikipedia article HTML only",
        "totals": dict(totals),
        "films": films,
        "passage_references": passage_rows,
        "limitations": [
            "An outbound reference URL is a locator, not validation of the source or its claim.",
            "References without an external URL remain unresolved for this audit; this does not mean they lack a valid bibliographic target.",
            "No reference text, article passage text, or working-corpus record is written by this audit.",
            "Wikipedia prose remains CC BY-SA 4.0; linked sources have independent terms and rights.",
        ],
    }


def render_catalog_citation_audit(report: dict[str, Any]) -> str:
    totals = report["totals"]
    resolved = totals.get("external_url_marker_occurrences", 0)
    markers = totals.get("marker_occurrences", 0)
    ratio = resolved / markers if markers else 0
    lines = [
        "# Ten-film citation-target audit", "",
        f"Films: {totals.get('films', 0)}; passages: {totals.get('passages', 0)}",
        f"Passages with citation markers: {totals.get('cited_passages', 0)}; all markers resolve to a reference-list entry: {totals.get('fully_reference_resolved_passages', 0)}; all markers have an external URL: {totals.get('fully_external_url_linked_passages', 0)}",
        f"Marker occurrences with an external reference URL: {resolved}/{markers} ({ratio:.1%})",
        f"Marker occurrences with no reference-list entry: {totals.get('markers_without_reference_entry', 0)}; with no external URL: {totals.get('markers_without_external_url', 0)}",
        "", "| Film | Passages | Cited | Reference-list resolved | All URL-linked | Markers | Reference-list markers | URL markers | No ref entry | No URL |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for film in report["films"]:
        lines.append(
            f"| {film['title']} | {film['passages']} | {film['cited_passages']} | "
            f"{film['fully_reference_resolved_passages']} | {film['fully_external_url_linked_passages']} | "
            f"{film['marker_occurrences']} | {film['reference_list_marker_occurrences']} | "
            f"{film['external_url_marker_occurrences']} | {film['markers_without_reference_entry']} | "
            f"{film['markers_without_external_url']} |"
        )
    lines.extend(["", "## Interpretation", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)
