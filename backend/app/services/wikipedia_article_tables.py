"""Extract review-only table structure from a retained Wikipedia HTML capture.

This adapter never creates facts or passages. Cell spans are retained rather
than guessed into an expanded grid; reviewers can inspect the original source.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import re

from app.services.wikipedia_article_html import (
    ArticlePageParseError, COMBINED_REFERENCE_HEADINGS, MAX_HTML_BYTES,
    SKIP_TOP_LEVEL, _metadata, _slug, validate_article_url,
)

TABLE_PARSER_VERSION = "enwiki-wikitable-review-v2"


@dataclass(frozen=True)
class TableCell:
    kind: str
    text: str
    rowspan: int
    colspan: int
    scope: str | None
    citation_markers: tuple[str, ...]


@dataclass(frozen=True)
class SourceTable:
    section_id: str
    section_locator: str
    section_title: str
    ordinal: int
    caption: str
    rows: tuple[tuple[TableCell, ...], ...]
    warnings: tuple[str, ...]


def _clean(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _span(value: str | None) -> int:
    if value is None:
        return 1
    if not value.isdigit() or not 1 <= int(value) <= 1000:
        raise ArticlePageParseError("Unsupported table cell span; review required.")
    return int(value)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.content_depth = 0
        self.main_depth = 0
        self.stack: list[tuple[str, bool, bool]] = []
        self.section_id = "0"
        self.headings: dict[int, str] = {}
        self.heading: int | None = None
        self.heading_parts: list[str] = []
        self.title = "Lead"
        self.locator = "lead"
        self.blocked = False
        self.table_depth = 0
        self.rows: list[tuple[TableCell, ...]] = []
        self.row: list[TableCell] | None = None
        self.cell: dict | None = None
        self.caption: list[str] | None = None
        self.caption_text = ""
        self.citation_depth = 0
        self.warnings: set[str] = set()
        self.tables: list[SourceTable] = []
        self.ordinals: dict[tuple[str, str], int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        content = tag == "div" and values.get("id") == "mw-content-text"
        main = tag == "div" and "mw-parser-output" in classes and self.content_depth > 0
        was_main = self.main_depth > 0
        if content:
            self.content_depth += 1
        tracks_main = main or (was_main and tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})
        if tracks_main:
            self.main_depth += 1
        self.stack.append((tag, content, tracks_main))
        if not self.main_depth:
            return
        if tag == "section" and values.get("data-mw-section-id") is not None and not self.table_depth:
            self.section_id = str(values["data-mw-section-id"])
        if self.table_depth:
            if tag == "table":
                self.table_depth += 1
                self.warnings.add("nested_table")
            elif self.table_depth == 1:
                if tag == "tr":
                    if self.row is not None:
                        raise ArticlePageParseError("Nested or unclosed table row.")
                    self.row = []
                elif tag in {"td", "th"}:
                    if self.row is None or self.cell is not None:
                        raise ArticlePageParseError("Unexpected table cell structure.")
                    self.cell = {"kind": tag, "parts": [], "rowspan": _span(values.get("rowspan")),
                                 "colspan": _span(values.get("colspan")), "scope": values.get("scope"), "refs": []}
                elif tag == "caption" and self.cell is None:
                    self.caption = []
                elif tag == "sup" and "reference" in classes and self.cell is not None:
                    marker = values.get("id")
                    if marker and marker.startswith("cite_ref-"):
                        self.cell["refs"].append(marker)
                    self.citation_depth += 1
                elif tag == "br" and self.cell is not None:
                    self.cell["parts"].append(" ")
                elif tag in {"img", "math"}:
                    # Meaning may be carried visually; never infer it as text.
                    self.warnings.add(f"{tag}_content_requires_review")
            return
        if tag == "table" and "wikitable" in classes and not self.blocked and "infobox" not in classes:
            self.table_depth = 1
            self.rows, self.row, self.cell = [], None, None
            self.caption, self.caption_text, self.warnings = None, "", set()
        elif tag in {"h2", "h3", "h4", "h5", "h6"}:
            self.heading = int(tag[1])
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.table_depth == 1 and not self.citation_depth:
            if self.cell is not None:
                self.cell["parts"].append(data)
            elif self.caption is not None:
                self.caption.append(data)
        elif not self.table_depth and self.heading is not None:
            self.heading_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.table_depth:
            if tag == "table":
                self.table_depth -= 1
                if self.table_depth == 0:
                    if self.row is not None or self.cell is not None:
                        raise ArticlePageParseError("Unclosed table row or cell.")
                    key = (self.section_id, self.locator)
                    ordinal = self.ordinals.get(key, 0)
                    self.ordinals[key] = ordinal + 1
                    self.tables.append(SourceTable(self.section_id, self.locator, self.title, ordinal,
                                                   self.caption_text, tuple(self.rows), tuple(sorted(self.warnings))))
            elif self.table_depth == 1:
                if tag == "sup" and self.citation_depth:
                    self.citation_depth -= 1
                elif tag in {"td", "th"} and self.cell is not None:
                    cell = self.cell
                    assert self.row is not None
                    self.row.append(TableCell(cell["kind"], _clean(cell["parts"]), cell["rowspan"],
                                              cell["colspan"], cell["scope"], tuple(dict.fromkeys(cell["refs"]))))
                    self.cell = None
                elif tag == "tr" and self.row is not None:
                    if self.cell is not None:
                        raise ArticlePageParseError("Unclosed table cell.")
                    self.rows.append(tuple(self.row))
                    self.row = None
                elif tag == "caption" and self.caption is not None:
                    self.caption_text = _clean(self.caption)
                    self.caption = None
        elif self.heading is not None and tag == f"h{self.heading}":
            title = _clean(self.heading_parts)
            level = self.heading
            if title:
                self.headings[level] = title
                self.headings = {key: value for key, value in self.headings.items() if key <= level}
                path = [self.headings[key] for key in sorted(self.headings)]
                self.title = " / ".join(path)
                self.locator = "/".join(_slug(value) for value in path)
                if level == 2:
                    self.blocked = title.casefold() in SKIP_TOP_LEVEL | COMBINED_REFERENCE_HEADINGS
            self.heading = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                for _, content, main in reversed(self.stack[index:]):
                    self.content_depth -= int(content)
                    self.main_depth -= int(main)
                del self.stack[index:]
                break


def extract_review_tables(payload: bytes, *, canonical_url: str, expected_qid: str):
    """Return identified source metadata and raw structured tables for review."""
    if not payload or len(payload) > MAX_HTML_BYTES:
        raise ArticlePageParseError("Article HTML is empty or exceeds the safety limit.")
    canonical_url = validate_article_url(canonical_url)
    try:
        html = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArticlePageParseError("Article HTML is not UTF-8.") from exc
    metadata = _metadata(html, canonical_url)
    if metadata.wikidata_id != expected_qid:
        raise ArticlePageParseError("Article identity mismatch.")
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    if parser.table_depth:
        raise ArticlePageParseError("Unclosed table.")
    return metadata, tuple(parser.tables)
