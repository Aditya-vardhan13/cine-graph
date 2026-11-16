import pytest
import hashlib
import json
from pathlib import Path

from app.services.wikipedia_article_html import ArticlePageParseError
from app.services.wikipedia_article_tables import extract_review_tables
from scripts.capture_writer_wikipedia_refresh import retained_payload
from scripts.prepare_wikipedia_table_review import prepare


def article(body: str) -> bytes:
    return ('''<script>{"wgTitle":"Example","wgArticleId":42,"wgWikibaseItemId":"Q42","wgRevisionId":17}</script>
    <div id="mw-content-text"><div class="mw-parser-output">''' + body + "</div></div>").encode()


def extract(body: str):
    return extract_review_tables(article(body), canonical_url="https://en.wikipedia.org/wiki/Example", expected_qid="Q42")[1]


def test_cells_spans_citations_and_sections_remain_source_bound():
    tables = extract('''<section data-mw-section-id="3"><h2>Release</h2><h3>Distribution</h3>
      <table class="wikitable"><caption>Territories</caption><tr><th>Distributor</th><th>Area</th></tr>
      <tr><td rowspan="2">Film Co<sup class="reference" id="cite_ref-1"><a>[1]</a></sup></td><td>India<br>and Nepal</td></tr>
      <tr><td colspan="2">Elsewhere</td></tr></table></section>''')
    table, = tables
    assert (table.section_id, table.section_locator, table.caption) == ("3", "release/distribution", "Territories")
    assert table.rows[1][0].text == "Film Co"
    assert table.rows[1][0].rowspan == 2
    assert table.rows[1][0].citation_markers == ("cite_ref-1",)
    assert table.rows[1][1].text == "India and Nepal"
    assert table.rows[2][0].colspan == 2


def test_excludes_infobox_and_reference_tables_and_reports_nested_tables():
    tables = extract('''<table class="infobox wikitable"><tr><td>Private</td></tr></table>
      <section data-mw-section-id="1"><h2>Accolades</h2><table class="wikitable"><tr><td>Outer
      <table><tr><td>Inner</td></tr></table></td></tr></table></section>
      <section data-mw-section-id="2"><h2>Notes and references</h2><table class="wikitable"><tr><td>Ref</td></tr></table></section>''')
    assert len(tables) == 1
    assert tables[0].warnings == ("nested_table",)
    assert tables[0].rows[0][0].text == "Outer"


def test_invalid_spans_and_wrong_identity_fail_closed():
    with pytest.raises(ArticlePageParseError, match="span"):
        extract('<table class="wikitable"><tr><td rowspan="0">X</td></tr></table>')
    with pytest.raises(ArticlePageParseError, match="identity"):
        extract_review_tables(article(""), canonical_url="https://en.wikipedia.org/wiki/Example", expected_qid="Q1")


def test_visual_cell_contents_are_flagged_for_review():
    tables = extract('<table class="wikitable"><tr><td><img alt="Winner" src="icon.png"></td></tr></table>')
    assert tables[0].warnings == ("img_content_requires_review",)
    assert tables[0].rows[0][0].text == ""


def test_retained_capture_produces_review_only_source_bound_tables():
    directory = Path("data/evaluation/writer-source-audit/wikipedia-refresh-v1")
    checkpoint = directory / "checkpoint.json"
    if not checkpoint.exists():
        pytest.skip("retained local capture unavailable")
    raw = checkpoint.read_bytes()
    qid = "Q21001674"
    capture = json.loads(raw)["captures"][qid]
    payload = retained_payload(directory, capture)
    result = prepare(qid, capture, payload, hashlib.sha256(raw).hexdigest())
    assert result["source_sha256"] == hashlib.sha256(payload).hexdigest()
    assert result["identity_status"] == result["rights_status"] == "review_required"
    assert result["product_ingested"] is False
    assert any(table["section_locator"] == "release/distribution" for table in result["tables"])
    with pytest.raises(ValueError, match="integrity"):
        prepare(qid, capture, payload + b" ", hashlib.sha256(raw).hexdigest())
