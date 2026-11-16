from pathlib import Path
import hashlib

import pytest

from app.services.wikipedia_article_html import (
    ArticlePageParseError,
    ArticlePageUrlError,
    COMBINED_REFERENCES_PARSER_VERSION,
    article_url,
    parse_article_html,
    validate_article_url,
)


FIXTURE = Path(__file__).parent / "fixtures" / "wikipedia-article-html-slice-v1.html"
ARTICLE_URL = "https://en.wikipedia.org/wiki/The_Dark_Knight"


def test_article_html_extracts_sectioned_prose_and_source_citations() -> None:
    document = parse_article_html(FIXTURE.read_bytes(), canonical_url=ARTICLE_URL, expected_qid="Q163872")

    assert document.parser_version == "enwiki-article-html-extraction-v6"
    assert (document.metadata.title, document.metadata.page_id, document.metadata.wikidata_id,
            document.metadata.revision_id) == ("The Dark Knight", 4276475, "Q163872", 1383150687)
    passages = {passage.section_locator: passage for passage in document.passages}
    assert set(passages) == {"lead", "plot", "production/development"}
    assert passages["plot"].citation_markers == ("cite_ref-1",)
    assert passages["plot"].citation_positions == (("cite_ref-1", 0, len(passages["plot"].content)),)
    assert all(
        set(passage.citation_markers) == {marker for marker, _, _ in passage.citation_positions}
        for passage in document.passages
    )
    assert all("mwrQ" not in passage.citation_markers for passage in document.passages)
    assert all("p. 10" not in passage.content for passage in document.passages)
    assert "Gotham's organized crime" in passages["plot"].content
    assert "Not narrative evidence" not in " ".join(item.content for item in document.passages)
    assert "reference section" not in " ".join(item.content for item in document.passages)
    assert "Bibliographic note" not in " ".join(item.content for item in document.passages)
    assert all(len(item.content) <= 1500 for item in document.passages)


def test_article_parser_fails_closed_on_wrong_film_identity() -> None:
    with pytest.raises(ArticlePageParseError, match="does not match expected film QID"):
        parse_article_html(FIXTURE.read_bytes(), canonical_url=ARTICLE_URL, expected_qid="Q999")


def test_candidate_parser_excludes_combined_references_without_hiding_other_sections() -> None:
    original = FIXTURE.read_bytes()
    combined = original.replace(b'<h2 id="References">References</h2>',
                                b'<h2 id="References">Notes and references</h2>')
    assert combined != original
    old = parse_article_html(combined, canonical_url=ARTICLE_URL)
    new = parse_article_html(combined, canonical_url=ARTICLE_URL,
                             parser_version=COMBINED_REFERENCES_PARSER_VERSION)
    assert any(p.section_locator == "notes-and-references" for p in old.passages)
    assert not any(p.section_locator.startswith("notes-and-references") for p in new.passages)
    assert [p for p in old.passages if not p.section_locator.startswith("notes-and-references")] == list(new.passages)
    assert new.parser_version == COMBINED_REFERENCES_PARSER_VERSION
    other = original.replace(b'<h2 id="References">References</h2>',
                             b'<h2 id="References">References in popular culture</h2>')
    assert any(p.section_locator == "references-in-popular-culture" for p in
               parse_article_html(other, canonical_url=ARTICLE_URL,
                                  parser_version=COMBINED_REFERENCES_PARSER_VERSION).passages)


def test_article_parser_rejects_unknown_version() -> None:
    with pytest.raises(ValueError, match="Unsupported Wikipedia article parser version"):
        parse_article_html(FIXTURE.read_bytes(), canonical_url=ARTICLE_URL, parser_version="unreviewed")


def test_candidate_parser_on_retained_paprika_source() -> None:
    digest = "f88f73afb87638d4f86f9deedaf2dee3ef0ea25d6cc802a79395d743a179b9cf"
    path = Path(f"data/evaluation/writer-source-audit/wikipedia-refresh-v1/snapshots/{digest}.html")
    if not path.exists():
        pytest.skip("retained local article not available")
    payload = path.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == digest
    url = "https://en.wikipedia.org/wiki/Paprika_(2006_film)"
    old = parse_article_html(payload, canonical_url=url, expected_qid="Q578595")
    new = parse_article_html(payload, canonical_url=url, expected_qid="Q578595",
                             parser_version=COMBINED_REFERENCES_PARSER_VERSION)
    removed = [p for p in old.passages if p.section_locator.startswith("notes-and-references")]
    assert removed and all("notes-and-references" not in p.section_locator for p in new.passages)
    assert [p for p in old.passages if p not in removed] == list(new.passages)


@pytest.mark.parametrize("url", [
    "http://en.wikipedia.org/wiki/The_Dark_Knight",
    "https://en.wikipedia.org/w/api.php?action=query",
    "https://en.wikipedia.org/wiki/The_Dark_Knight?oldid=123",
    "https://en.wikipedia.org/wiki/../w/api.php",
    "https://en.wikipedia.org.evil.example/wiki/The_Dark_Knight",
    "https://user@en.wikipedia.org/wiki/The_Dark_Knight",
    "https://en.wikipedia.org:443/wiki/The_Dark_Knight",
])
def test_only_ordinary_https_article_urls_are_supported(url: str) -> None:
    with pytest.raises(ArticlePageUrlError):
        validate_article_url(url)


def test_title_to_article_url_encodes_path_and_canonicalizes_whitespace() -> None:
    assert article_url("The   Dark Knight") == ARTICLE_URL
