"""Additive parser canary preserving visible content in `lang` templates."""
from __future__ import annotations

from app.services.wikipedia_text_v2 import chunk_section_v2, readable_wikitext as read_v2
from app.services.wikipedia_passages_v2 import derive_passages as derive_v2
from app.services.wikipedia_research import split_sections

EXTRACTION_VERSION = "enwiki-readable-prose-mwparser-v3-lang"


def readable_wikitext(value: str):
    return read_v2(value, preserve_language_templates=True)


def chunk_section(value: str):
    return chunk_section_v2(value, reader=readable_wikitext)


def derive_passages(wikitext: str):
    def sections(value):
        def is_substantive(text):
            parsed = readable_wikitext(text)
            return bool(parsed.text or parsed.media_captions)
        return split_sections(value, is_substantive=is_substantive)
    return derive_v2(wikitext, reader=readable_wikitext, chunker=chunk_section, section_splitter=sections)
