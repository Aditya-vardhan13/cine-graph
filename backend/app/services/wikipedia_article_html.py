"""Deterministic extraction from a retained English Wikipedia article page.

This module is pure: it does not fetch, persist, resolve film identity, or
promote narrative prose into facts. The caller must retain the original HTML
bytes and apply the source policy before using this parser.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import hashlib
import json
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit


PARSER_VERSION = "enwiki-article-html-extraction-v6"
SKIP_TOP_LEVEL = {
    "notes", "references", "external links", "see also", "bibliography",
    "works cited", "further reading", "external links", "sources",
}
SKIP_CLASSES = {
    "ambox", "coordinates", "editsection", "hatnote", "infobox",
    "metadata", "navbox", "navigation-not-searchable", "noprint",
    "shortdescription", "side-box", "toc", "vertical-navbox", "thumb",
    "thumbcaption", "thumbinner", "gallery", "gallerybox",
}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
MAX_HTML_BYTES = 15 * 1024 * 1024


class ArticlePageParseError(ValueError):
    """The response is not a complete, identified Wikipedia article page."""


class ArticlePageUrlError(ValueError):
    """The URL is not an ordinary English Wikipedia article-page URL."""


@dataclass(frozen=True)
class ArticleMetadata:
    title: str
    page_id: int
    wikidata_id: str
    revision_id: int
    canonical_url: str


@dataclass(frozen=True)
class ArticlePassage:
    section_locator: str
    section_title: str
    ordinal: int
    content: str
    citation_markers: tuple[str, ...]
    # (marker ID, paragraph index within passage, character offset in passage)
    citation_positions: tuple[tuple[str, int, int], ...]

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArticleDocument:
    metadata: ArticleMetadata
    passages: tuple[ArticlePassage, ...]
    parser_version: str = PARSER_VERSION


def article_url(title: str) -> str:
    """Build an article URL from a known sitelink title, never from free URL input."""
    title = re.sub(r"\s+", " ", title).strip()
    if not title or len(title) > 255 or title.startswith(("/", "#")):
        raise ArticlePageUrlError("A valid Wikipedia article title is required.")
    path_title = quote(title.replace(" ", "_"), safe="()_,-")
    return f"https://en.wikipedia.org/wiki/{path_title}"


def validate_article_url(url: str) -> str:
    """Accept only HTTPS enwiki article paths, without query or fragment tricks."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ArticlePageUrlError("Wikipedia article URL contains an invalid authority.") from exc
    if (parts.scheme != "https" or parts.hostname != "en.wikipedia.org"
            or parts.username or parts.password or port
            or not parts.path.startswith("/wiki/") or parts.query or parts.fragment):
        raise ArticlePageUrlError("Only https://en.wikipedia.org/wiki/{article} URLs are supported.")
    decoded_path = unquote(parts.path)
    title = decoded_path.removeprefix("/wiki/")
    if not title or title.startswith(("/", "#")):
        raise ArticlePageUrlError("Wikipedia URL does not identify an article title.")
    if any(part in {".", ".."} for part in decoded_path.split("/")):
        raise ArticlePageUrlError("Wikipedia article path contains a traversal segment.")
    return urlunsplit(("https", "en.wikipedia.org", parts.path, "", ""))


def _config_value(html: str, key: str, pattern: str) -> str | None:
    match = re.search(pattern, html)
    return match.group(1) if match else None


def _metadata(html: str, canonical_url: str) -> ArticleMetadata:
    title_value = _config_value(html, "wgTitle", r'"wgTitle"\s*:\s*("(?:\\.|[^"\\])*")')
    page_id = _config_value(html, "wgArticleId", r'"wgArticleId"\s*:\s*(\d+)')
    qid = _config_value(html, "wgWikibaseItemId", r'"wgWikibaseItemId"\s*:\s*"(Q\d+)"')
    revision = _config_value(html, "wgRevisionId", r'"wgRevisionId"\s*:\s*(\d+)')
    if not all((title_value, page_id, qid, revision)):
        raise ArticlePageParseError("Article HTML is missing title, page ID, Wikidata ID, or revision ID.")
    try:
        title = json.loads(title_value)
        page_number, revision_number = int(page_id), int(revision)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ArticlePageParseError("Article metadata is malformed.") from exc
    return ArticleMetadata(title, page_number, qid, revision_number, canonical_url)


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "section"


class _ArticleContentParser(HTMLParser):
    """Extract prose blocks from mw-parser-output, excluding chrome and tables."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.content_depth = 0
        self.main_depth = 0
        self.skip_depth = 0
        self.stack: list[tuple[str, bool, bool, bool]] = []
        self.section_id = "0"
        self.heading_levels: dict[int, str] = {}
        self.heading_level: int | None = None
        self.heading_parts: list[str] = []
        self.current_title = "Lead"
        self.current_locator = "lead"
        self.section_blocked = False
        self.paragraph_tag: str | None = None
        self.paragraph_parts: list[str] = []
        self.citation: list[str] | None = None
        self.citations: list[str] = []
        self.citation_offsets: list[tuple[str, int]] = []
        self.records: list[tuple[str, str, str, tuple[str, ...], str, tuple[tuple[str, int], ...]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        is_content = tag == "div" and values.get("id") == "mw-content-text"
        is_main = (tag == "div" and "mw-parser-output" in classes and self.content_depth > 0)
        was_main = self.main_depth > 0
        if is_content:
            self.content_depth += 1
        if is_main:
            self.main_depth += 1
        elif was_main and tag not in VOID_TAGS:
            self.main_depth += 1

        in_main = self.main_depth > 0
        is_section = in_main and tag == "section" and values.get("data-mw-section-id") is not None
        if is_section:
            self.section_id = str(values["data-mw-section-id"])
        marker = bool(in_main and tag == "sup" and "reference" in classes
                      and (values.get("id") or "").startswith("cite_ref-"))
        blocked_class = bool(classes & SKIP_CLASSES)
        is_skip = bool(in_main and (tag in {"table", "style", "script", "noscript", "figure", "math"}
                                    or blocked_class or (tag == "sup" and not marker)))
        if is_skip:
            self.skip_depth += 1
        self.stack.append((tag, is_content, is_main or (was_main and tag not in VOID_TAGS), is_skip))

        if not in_main or self.skip_depth:
            if marker and not self.skip_depth and self.paragraph_tag and values.get("id"):
                self.citation = [str(values["id"])]
            return
        if marker:
            href = values.get("id") or "inline-reference"
            self.citations.append(str(href))
            self.citation_offsets.append((str(href), sum(len(part) for part in self.paragraph_parts)))
            self.citation = [str(href)]
            return
        if tag == "section" and self.paragraph_tag:
            self._finish_paragraph()
        if tag == "h2" or tag == "h3" or tag == "h4" or tag == "h5" or tag == "h6":
            self.heading_level = int(tag[1])
            self.heading_parts = []
        elif tag in {"p", "li", "blockquote"} and self.paragraph_tag is None and not self.section_blocked:
            self.paragraph_tag = tag
            self.paragraph_parts = []
            self.citations = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "sup" and self.citation is not None:
            self.citation = None
        if self.heading_level is not None and tag == f"h{self.heading_level}":
            title = re.sub(r"\s+", " ", "".join(self.heading_parts)).strip()
            level = self.heading_level
            if title:
                self.heading_levels[level] = title
                for deeper in list(self.heading_levels):
                    if deeper > level:
                        del self.heading_levels[deeper]
                path = [self.heading_levels[key] for key in sorted(self.heading_levels)]
                self.current_title = " / ".join(path)
                self.current_locator = "/".join(_slug(part) for part in path)
                if level == 2:
                    self.section_blocked = title.casefold() in SKIP_TOP_LEVEL
            self.heading_level = None
            self.heading_parts = []
        if self.paragraph_tag == tag:
            self._finish_paragraph()

        # HTMLParser does not expose a DOM stack; close matching open tags to
        # remain tolerant of void and imperfectly nested elements.
        for index in range(len(self.stack) - 1, -1, -1):
            open_tag, _, _, _ = self.stack[index]
            if open_tag != tag:
                continue
            closing = self.stack[index:]
            del self.stack[index:]
            for _, content_flag, main_flag, skip_flag in reversed(closing):
                if content_flag:
                    self.content_depth = max(0, self.content_depth - 1)
                if main_flag:
                    self.main_depth = max(0, self.main_depth - 1)
                if skip_flag:
                    self.skip_depth = max(0, self.skip_depth - 1)
            break

    def handle_data(self, data: str) -> None:
        if self.heading_level is not None and not self.skip_depth:
            self.heading_parts.append(data)
        if self.citation is not None:
            return
        if self.paragraph_tag is not None and self.main_depth > 0 and not self.skip_depth:
            self.paragraph_parts.append(data)

    def _finish_paragraph(self) -> None:
        raw_text = "".join(self.paragraph_parts)
        text = re.sub(r"\s+", " ", raw_text).strip()
        if text and not self.section_blocked:
            positions = []
            for marker, raw_offset in self.citation_offsets:
                prefix = re.sub(r"\s+", " ", raw_text[:raw_offset]).strip()
                positions.append((marker, len(prefix)))
            self.records.append((self.section_id, self.current_locator, self.current_title,
                                 tuple(dict.fromkeys(self.citations)), text, tuple(positions)))
        self.paragraph_tag = None
        self.paragraph_parts = []
        self.citations = []
        self.citation_offsets = []


def parse_article_html(payload: bytes, *, canonical_url: str, expected_qid: str | None = None,
                       chunk_limit: int = 1500) -> ArticleDocument:
    """Extract bounded prose from a retained article response, validating identity."""
    if not payload or len(payload) > MAX_HTML_BYTES:
        raise ArticlePageParseError("Article HTML is empty or exceeds the 15 MiB safety limit.")
    canonical_url = validate_article_url(canonical_url)
    try:
        html = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArticlePageParseError("English Wikipedia article response is not valid UTF-8.") from exc
    metadata = _metadata(html, canonical_url)
    if expected_qid and metadata.wikidata_id != expected_qid:
        raise ArticlePageParseError(
            f"Article QID {metadata.wikidata_id} does not match expected film QID {expected_qid}."
        )
    parser = _ArticleContentParser()
    parser.feed(html)
    parser.close()
    # Record layout is section id, locator, title, markers, content and offsets.
    blocks = parser.records
    by_section: dict[tuple[str, str, str], list[tuple[str, tuple[str, ...], tuple[tuple[str, int], ...]]]] = {}
    for section_id, locator, title, citations, content, positions in blocks:
        by_section.setdefault((section_id, locator, title), []).append((content, citations, positions))

    passages: list[ArticlePassage] = []
    duplicate_locators: dict[str, int] = {}
    for _, locator, _ in by_section:
        duplicate_locators[locator] = duplicate_locators.get(locator, 0) + 1
    for (section_id, locator, title), paragraphs in by_section.items():
        display_locator = f"{locator}#mw-section-{section_id}" if duplicate_locators[locator] > 1 else locator
        buffer: list[str] = []
        markers: list[str] = []
        position_rows: list[tuple[str, int, int]] = []
        ordinal = 0
        for text, refs, positions in paragraphs:
            candidate = "\n\n".join([*buffer, text])
            if buffer and len(candidate) > chunk_limit:
                content = "\n\n".join(buffer)
                passages.append(ArticlePassage(display_locator, title, ordinal, content,
                                               tuple(dict.fromkeys(marker for marker, _, _ in position_rows)),
                                               tuple(position_rows)))
                ordinal += 1
                buffer, markers = [text], list(refs)
                position_rows = [(marker, 0, offset) for marker, offset in positions]
            else:
                paragraph_index = len(buffer)
                base_offset = len("\n\n".join(buffer)) + (2 if buffer else 0)
                buffer.append(text)
                markers.extend(refs)
                position_rows.extend((marker, paragraph_index, base_offset + offset)
                                     for marker, offset in positions)
        if buffer:
            passages.append(ArticlePassage(
                display_locator, title, ordinal, "\n\n".join(buffer),
                tuple(dict.fromkeys(marker for marker, _, _ in position_rows)),
                tuple(position_rows),
            ))
    if not passages:
        raise ArticlePageParseError("Article page has no extractable prose passages.")
    return ArticleDocument(metadata, tuple(passages))
