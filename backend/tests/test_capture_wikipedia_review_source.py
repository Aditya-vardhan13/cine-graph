from pathlib import Path

import pytest

from app.services.wikipedia_article_html import ArticlePageParseError
from scripts.capture_wikipedia_review_source import validate_capture


def test_review_capture_requires_both_expected_qid_and_page_id():
    payload = (Path(__file__).parent / "fixtures" / "wikipedia-article-html-slice-v1.html").read_bytes()
    arguments = {"canonical_url": "https://en.wikipedia.org/wiki/The_Dark_Knight",
                 "expected_qid": "Q163872", "expected_page_id": 4276475}
    assert validate_capture(payload, **arguments).metadata.revision_id == 1383150687
    with pytest.raises(ArticlePageParseError, match="does not match"):
        validate_capture(payload, **{**arguments, "expected_qid": "Q1"})
    with pytest.raises(ValueError, match="page ID differs"):
        validate_capture(payload, **{**arguments, "expected_page_id": 1})
