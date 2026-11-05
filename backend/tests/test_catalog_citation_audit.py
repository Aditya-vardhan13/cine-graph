from app.services.catalog_citation_audit import citation_reference_index
from app.services.catalog_pilot_reextract import derive_catalog_pilot
from app.services.catalog_citation_audit import audit_catalog_citations
from hashlib import sha256
import json
from pathlib import Path


def test_citation_marker_resolves_to_reference_id_and_external_url() -> None:
    payload = b"""<div><p>Text<sup class='reference' id='cite_ref-1'>
      <a href='#cite_note-1'>[1]</a></sup></p></div>
      <ol><li id='cite_note-1'><span class='reference-text'>Record
      <a href='https://example.org/source'>source</a></span></li></ol>"""

    assert citation_reference_index(payload) == {
        "cite_ref-1": {
            "reference_ids": ["cite_note-1"],
            "reference_entry_present": True,
            "reference_ids_without_external_url": [],
            "external_urls": ["https://example.org/source"],
        }
    }


def test_reference_without_external_url_is_present_but_not_url_resolved() -> None:
    payload = b"""<sup class='reference' id='cite_ref-book'>
      <a href='#cite_note-book'>[book]</a></sup>
      <ol><li id='cite_note-book'><span class='reference-text'>Print source</span></li></ol>"""

    assert citation_reference_index(payload) == {
        "cite_ref-book": {
            "reference_ids": ["cite_note-book"],
            "reference_entry_present": True,
            "reference_ids_without_external_url": ["cite_note-book"],
            "external_urls": [],
        }
    }


def test_citation_marker_with_missing_reference_entry_is_not_claimed_resolved() -> None:
    payload = b"<sup class='reference' id='cite_ref-missing'><a href='#cite_note-missing'>[?]</a></sup>"

    assert citation_reference_index(payload) == {
        "cite_ref-missing": {
            "reference_ids": ["cite_note-missing"],
            "reference_entry_present": False,
            "reference_ids_without_external_url": ["cite_note-missing"],
            "external_urls": [],
        }
    }


def test_pilot_citation_audit_uses_versioned_derivative_and_counts_reference_urls(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "wikipedia-article-html-slice-v1.html"
    source = fixture.read_bytes()
    source_rel = "snapshots/wikipedia/Q163872/article.html"
    source_path = tmp_path / source_rel
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source)
    (tmp_path / "capture-manifest.json").write_text(json.dumps({
        "schema": "cinegraph.catalog-pilot-capture/v1",
        "selection_sha256": "selection-hash",
        "films": [{
            "capture_status": "complete",
            "wikipedia_status": "captured",
            "qid": "Q163872",
            "title": "The Dark Knight",
            "year": 2008,
            "wikipedia_snapshot_path": source_rel,
            "wikipedia_sha256": sha256(source).hexdigest(),
            "wikipedia_revision": 1383150687,
            "wikipedia_capture_url": "https://en.wikipedia.org/wiki/The_Dark_Knight",
            "wikipedia_title_resolved": "The Dark Knight",
            "passage_derivative_path": "unused-v1.json",
        }],
    }), encoding="utf-8")

    derive_catalog_pilot(tmp_path)
    report = audit_catalog_citations(tmp_path)

    assert report["totals"]["marker_occurrences"] == 1
    assert report["totals"]["reference_list_marker_occurrences"] == 1
    assert report["totals"]["external_url_marker_occurrences"] == 1
    assert report["totals"]["markers_without_reference_entry"] == 0
