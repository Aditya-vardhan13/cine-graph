from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.services.catalog_pilot_reextract import (
    CatalogPilotExtractionError, audit_catalog_pilot_extraction, derive_catalog_pilot,
    validate_citation_positions,
)
from app.services.wikipedia_article_html import ArticlePassage


FIXTURE = Path(__file__).parent / "fixtures" / "wikipedia-article-html-slice-v1.html"


def test_citation_position_must_belong_to_declared_paragraph() -> None:
    valid = ArticlePassage("plot", "Plot", 0, "First.\n\nSecond.", ("ref",), (("ref", 1, 14),))
    validate_citation_positions(valid)
    invalid = ArticlePassage("plot", "Plot", 0, "First.\n\nSecond.", ("ref",), (("ref", 0, 14),))
    with pytest.raises(CatalogPilotExtractionError, match="outside its paragraph"):
        validate_citation_positions(invalid)


def test_reextract_creates_a_new_immutable_version_and_leaves_v1_untouched(tmp_path: Path) -> None:
    source = FIXTURE.read_bytes()
    source_path = tmp_path / "snapshots/wikipedia/Q163872/article.html"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    old_v1 = tmp_path / "snapshots/wikipedia-passages/Q163872/old-v1.json"
    old_v1.parent.mkdir(parents=True)
    old_v1.write_bytes(b"v1 derivative stays immutable")
    (tmp_path / "capture-manifest.json").write_text(json.dumps({
        "schema": "cinegraph.catalog-pilot-capture/v1",
        "selection_sha256": "selection-hash",
        "films": [{
            "capture_status": "complete",
            "wikipedia_status": "captured",
            "wikipedia_snapshot_path": source_path.relative_to(tmp_path).as_posix(),
            "wikipedia_sha256": sha256(source).hexdigest(),
            "wikipedia_capture_url": "https://en.wikipedia.org/wiki/The_Dark_Knight",
            "wikipedia_revision": 1383150687,
            "wikipedia_title_resolved": "The Dark Knight",
            "passage_derivative_path": old_v1.relative_to(tmp_path).as_posix(),
            "qid": "Q163872",
            "title": "The Dark Knight",
            "year": 2008,
        }],
    }), encoding="utf-8")

    manifest = derive_catalog_pilot(tmp_path)
    report = audit_catalog_pilot_extraction(tmp_path, manifest)

    assert report["pass"] is True
    assert report["audited_films"] == 1
    assert report["total_passages"] == 3
    assert report["citation_marker_occurrences"] == 1
    assert old_v1.read_bytes() == b"v1 derivative stays immutable"
    assert (tmp_path / "extraction-manifest-6.json").is_file()
    assert manifest["films"][0]["passage_derivative_path"].startswith("snapshots/wikipedia-passages-v6/")
    assert derive_catalog_pilot(tmp_path) == manifest
