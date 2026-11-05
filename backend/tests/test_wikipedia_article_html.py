from pathlib import Path

import pytest

from app.services.wikipedia_article_html import (
    ArticlePageParseError,
    ArticlePageUrlError,
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
