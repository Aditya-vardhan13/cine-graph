"""Versioned, read-only wikitext text extraction for a retained-source canary.

This does not replace the v1 narrative passages or mutate any snapshot. The
output deliberately separates narrative text from citation and media markup;
downstream passage persistence needs an explicit versioned migration after
source-quality review.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from collections.abc import Iterable

import mwparserfromhell
from mwparserfromhell.nodes import Text


EXTRACTION_VERSION = "enwiki-readable-prose-mwparser-v2"
_MEDIA_PREFIXES = ("file:", "image:")
_PRESENTATION_TAGS = {"ref", "references", "gallery"}


@dataclass(frozen=True)
class ReadableWikitext:
    text: str
    removed_media: tuple[str, ...]
    media_captions: tuple[str, ...]
    removed_citations: tuple[str, ...]


def _media_caption(link) -> str:
    """Take the final top-level File parameter, not pipes inside nested links."""
    if link.text is None:
        return ""
    parameters = [""]
    for node in link.text.nodes:
        if isinstance(node, Text):
            parts = str(node).split("|")
            parameters[-1] += parts[0]
            parameters.extend(parts[1:])
        else:
            parameters[-1] += str(node)
    caption = parameters[-1].strip()
    if not caption or caption.casefold() in {"thumb", "thumbnail", "left", "right", "center", "none", "frameless"}:
        return ""
    text = mwparserfromhell.parse(caption, skip_style_tags=True).strip_code()
    return re.sub(r"\s+", " ", unescape(re.sub(r"'{2,5}", "", text))).strip()


def readable_wikitext(value: str) -> ReadableWikitext:
    """Strip nested syntax while keeping linked prose and the discarded provenance.

    Media links are handled explicitly because mwparserfromhell intentionally
    treats File links like ordinary links and would otherwise surface captions
    such as ``thumb|alt=...`` as if they were narrative sentences.
    """
    code = mwparserfromhell.parse(value, skip_style_tags=True)
    media = []
    captions = []
    for link in reversed(code.filter_wikilinks(recursive=True)):
        title = str(link.title).strip().casefold()
        if title.startswith(":") and title[1:].startswith(_MEDIA_PREFIXES):
            # A leading colon links to the file page; its display label is prose.
            code.replace(link, str(link.text or link.title))
        elif title.startswith(_MEDIA_PREFIXES):
            media.append(str(link))
            caption = _media_caption(link)
            if caption:
                captions.append(caption)
            code.remove(link)
    citations = []
    for tag in reversed(code.filter_tags(recursive=True)):
        if str(tag.tag).strip().casefold() in _PRESENTATION_TAGS:
            citations.append(str(tag))
            code.remove(tag)
    stripped = unescape(re.sub(r"'{2,5}", "", code.strip_code(normalize=True, collapse=True)))
    text = re.sub(r"\s+", " ", stripped).strip()
    return ReadableWikitext(
        text, tuple(reversed(media)), tuple(reversed(captions)), tuple(reversed(citations)),
    )


def chunk_section_v2(value: str, *, limit: int = 1500) -> Iterable[str]:
    """Group paragraphs without splitting a multiline citation or template.

    Only top-level text nodes contain real paragraph boundaries. A blank line
    inside ``<ref>`` or ``{{template}}`` belongs to that syntax node and must
    not create a new raw passage with an unclosed fragment.
    """
    if limit <= 0:
        raise ValueError("Paragraph limit must be positive.")
    current: list[str] = []
    paragraphs: list[str] = []
    for node in mwparserfromhell.parse(value, skip_style_tags=True).nodes:
        if isinstance(node, Text):
            for part in re.split(r"(\n[ \t]*\n)", str(node)):
                if re.fullmatch(r"\n[ \t]*\n", part):
                    paragraph = "".join(current).strip()
                    if paragraph:
                        paragraphs.append(paragraph)
                    current = []
                else:
                    current.append(part)
        else:
            current.append(str(node))
    paragraph = "".join(current).strip()
    if paragraph:
        paragraphs.append(paragraph)

    buffer = ""
    for paragraph in paragraphs:
        parsed = readable_wikitext(paragraph)
        if not parsed.text and not parsed.media_captions:
            continue
        if buffer and len(readable_wikitext(buffer).text) + len(parsed.text) > limit:
            yield buffer
            buffer = paragraph
        else:
            buffer = f"{buffer}\n\n{paragraph}".strip()
    if buffer:
        yield buffer
