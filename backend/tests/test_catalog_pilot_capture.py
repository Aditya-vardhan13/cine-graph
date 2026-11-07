import json
from hashlib import sha256
from pathlib import Path

import pytest

from app.services.catalog_pilot_capture import (
    CatalogPilotCaptureError,
    _atomic_write,
    _load_selection,
    _section_counts,
    _source_file,
)
from app.services.catalog_pilot_audit import (
    audit_capture_bundle,
    render_audit_markdown,
    missing_content_categories,
    section_categories,
    structured_metadata_coverage,
)
from scripts.audit_catalog_pilot import next_audit_output
from app.services.wikipedia_article_html import parse_article_html


def _selection_document(*, match_status: str = "exact_title_year", qids: tuple[str, ...] = ("Q123",)) -> dict:
    return {
        "films": [{
            "input_title": "Example Film",
            "input_year": 2000,
            "match_status": match_status,
            "catalog_candidates": [{"wikidata_id": qid} for qid in qids],
        }],
    }


def _english_selection_document() -> dict:
    films = []
    for rank in range(1, 4):
        films.append({
            "selection_rank": rank,
            "input_rank": rank + 5,
            "input_title": f"English Film {rank}",
            "input_year": 2000 + rank,
            "catalog_match": "exact_title_year",
            "catalog_film_id": f"film-{rank}",
            "catalog_title": f"English Film {rank}",
            "wikidata_id": f"Q{rank}",
            "catalog_language": "en",
        })
    return {"version": "english-catalog-pilot-v1", "film_count": len(films), "films": films}


def test_catalog_pilot_manifest_requires_unambiguous_title_year_and_qid(tmp_path: Path) -> None:
    source = tmp_path / "selection.json"
    source.write_text(json.dumps(_selection_document()), encoding="utf-8")

    rows, digest = _load_selection(source, 1)

    assert rows == [{"selection_rank": 1, "title": "Example Film", "year": 2000, "qid": "Q123"}]
    assert len(digest) == 64


def test_english_pilot_capture_supports_checkpointed_offset_batches(tmp_path: Path) -> None:
    source = tmp_path / "selection.json"
    source.write_text(json.dumps(_english_selection_document()), encoding="utf-8")

    rows, digest = _load_selection(source, 2, offset=1)

    assert rows == [
        {"selection_rank": 2, "title": "English Film 2", "year": 2002,
         "qid": "Q2", "catalog_film_id": "film-2"},
        {"selection_rank": 3, "title": "English Film 3", "year": 2003,
         "qid": "Q3", "catalog_film_id": "film-3"},
    ]
    assert len(digest) == 64


@pytest.mark.parametrize("mutation", ["language", "match", "missing_catalog_id", "missing_qid"])
def test_english_pilot_capture_rejects_unqualified_rows(tmp_path: Path, mutation: str) -> None:
    document = _english_selection_document()
    film = document["films"][0]
    if mutation == "language":
        film["catalog_language"] = "und"
    elif mutation == "match":
        film["catalog_match"] = "review_required_crosslink"
    elif mutation == "missing_catalog_id":
        film.pop("catalog_film_id")
    else:
        film.pop("wikidata_id")
    source = tmp_path / "selection.json"
    source.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CatalogPilotCaptureError, match="English exact-title/year"):
        _load_selection(source, 1)


def test_catalog_pilot_capture_rejects_out_of_range_offsets(tmp_path: Path) -> None:
    source = tmp_path / "selection.json"
    source.write_text(json.dumps(_english_selection_document()), encoding="utf-8")

    with pytest.raises(CatalogPilotCaptureError, match="requested number of films"):
        _load_selection(source, 2, offset=2)


@pytest.mark.parametrize(
    "document",
    [
        _selection_document(match_status="review_required"),
        _selection_document(qids=("Q123", "Q124")),
        _selection_document(qids=()),
    ],
)
def test_catalog_pilot_manifest_rejects_ambiguous_identity(tmp_path: Path, document: dict) -> None:
    source = tmp_path / "selection.json"
    source.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CatalogPilotCaptureError, match="unambiguous exact-title/year"):
        _load_selection(source, 1)


def test_capture_files_are_content_addressed_and_never_overwritten(tmp_path: Path) -> None:
    relative_path, digest = _source_file(tmp_path, "wikidata", "Q123", b"exact bytes", ".json")
    target = tmp_path / relative_path

    assert target.read_bytes() == b"exact bytes"
    assert digest in relative_path
    assert _source_file(tmp_path, "wikidata", "Q123", b"exact bytes", ".json") == (relative_path, digest)
    with pytest.raises(CatalogPilotCaptureError, match="Refusing to overwrite immutable capture"):
        _atomic_write(target, b"different")


def test_audit_cli_selects_next_report_version_without_overwriting(tmp_path: Path) -> None:
    (tmp_path / "capture-audit-v2.md").write_text("old", encoding="utf-8")
    (tmp_path / "capture-audit-v5.md").write_text("older", encoding="utf-8")
    (tmp_path / "capture-audit.md").write_text("legacy", encoding="utf-8")

    assert next_audit_output(tmp_path) == tmp_path / "capture-audit-v6.md"


def test_section_counts_preserve_nested_section_titles() -> None:
    class Passage:
        def __init__(self, section_title: str) -> None:
            self.section_title = section_title

    assert _section_counts((Passage("Lead"), Passage("Production / Casting"), Passage("Lead"))) == {
        "Lead": 2,
        "Production / Casting": 1,
    }


def test_structured_metadata_coverage_counts_values_and_role_qualifiers() -> None:
    claims = {
        "P577": [
            {"mainsnak": {"datavalue": {"value": {"time": "+2008-01-01T00:00:00Z", "precision": 11}}},
             "qualifiers": {"P291": [{"datavalue": {"value": {"id": "Q30"}}}]},
             "references": [{}]},
            {"rank": "deprecated", "mainsnak": {"datavalue": {"value": {"precision": 9}}}},
        ],
        "P2047": [{"mainsnak": {"datavalue": {"value": {"amount": "+152"}}}, "references": [{}]}],
        "P161": [
            {"mainsnak": {"datavalue": {"value": {"id": "Q1"}}},
             "qualifiers": {"P453": [{"datavalue": {"value": {"id": "Q2"}}}]}},
            {"mainsnak": {"datavalue": {"value": {"id": "Q3"}}},
             "qualifiers": {"P4633": [{"datavalue": {"value": "The Joker"}}]}},
            {"mainsnak": {"datavalue": {"value": {"id": "Q4"}}}},
        ],
    }

    coverage = structured_metadata_coverage(claims)

    assert coverage["value_statement_counts"]["release_date"] == 1
    assert coverage["release_date_precision_counts"] == {"11": 1}
    assert coverage["release_dates_with_territory"] == 1
    assert coverage["release_dates_with_references"] == 1
    assert coverage["runtime_values_with_references"] == 1
    assert coverage["cast_character_entity_qualifiers"] == 1
    assert coverage["cast_character_name_qualifiers"] == 1
    assert coverage["cast_with_character_qualifier"] == 2
    assert coverage["cast_without_character_qualifier"] == 1


def test_structured_metadata_coverage_ignores_malformed_claim_and_qualifier_shapes() -> None:
    claims = {
        "P577": [
            None,
            {"mainsnak": None},
            {"mainsnak": {"snaktype": "novalue", "datavalue": {"value": {"precision": 11}}}},
            {"mainsnak": {"datavalue": {"value": None}}},
            {"mainsnak": {"datavalue": {"value": {"time": "+2000-00-00T00:00:00Z", "precision": "11"}}},
             "qualifiers": {"P291": [{"snaktype": "somevalue"}, None]}, "references": "not-a-list"},
        ],
        "P161": [
            {"mainsnak": {"datavalue": {"value": {"id": "Q20"}}},
             "qualifiers": [
                 {"P453": [{"datavalue": {"value": {"id": "Q30"}}}]},
             ]},
            {"mainsnak": {"datavalue": {"value": {"id": "Q21"}}},
             "qualifiers": {
                 "P453": [{"snaktype": "value", "datavalue": {"value": {"id": "invalid"}}}],
                 "P4633": [{"snaktype": "somevalue"}],
             }},
        ],
    }

    coverage = structured_metadata_coverage(claims)

    assert coverage["value_statement_counts"]["release_date"] == 1
    assert coverage["release_date_precision_counts"] == {}
    assert coverage["release_dates_with_territory"] == 0
    assert coverage["release_dates_with_references"] == 0
    assert coverage["value_statement_counts"]["cast"] == 2
    assert coverage["cast_character_entity_qualifiers"] == 0
    assert coverage["cast_character_name_qualifiers"] == 0
    assert coverage["cast_with_character_qualifier"] == 0
    assert structured_metadata_coverage([{"P577": []}])["value_statement_counts"]["release_date"] == 0


def test_catalog_pilot_audit_reverifies_bytes_identity_and_parser_output(tmp_path: Path) -> None:
    fixture_root = Path(__file__).parent / "fixtures"
    html = (fixture_root / "wikipedia-article-html-slice-v1.html").read_bytes()
    entity = {
        "id": "Q163872",
        "lastrevid": 1,
        "labels": {"en": {"value": "The Dark Knight"}},
        "sitelinks": {"enwiki": {"title": "The Dark Knight"}},
        "claims": {
            "P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q11424"}}}}],
            "P577": [{"mainsnak": {"datavalue": {"value": {"time": "+2008-01-01T00:00:00Z", "precision": 11}}}}],
            "P57": [{"mainsnak": {"datavalue": {"value": {"id": "Q2"}}}}],
            "P161": [
                {"mainsnak": {"datavalue": {"value": {"id": "Q3"}}},
                 "qualifiers": {"P453": [{"datavalue": {"value": {"id": "Q4"}}}]}},
                {"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}},
            ],
        },
    }
    entity_bytes = json.dumps({"entities": {"Q163872": entity}}).encode()
    article_url = "https://en.wikipedia.org/wiki/The_Dark_Knight"
    document = parse_article_html(html, canonical_url=article_url, expected_qid="Q163872")
    derivative = {
        "schema": "cinegraph.wikipedia-passage-extraction/v3",
        "source_snapshot_sha256": sha256(html).hexdigest(),
        "source_revision": document.metadata.revision_id,
        "parser_version": document.parser_version,
        "passages": [
            {
                "section_locator": item.section_locator,
                "section_title": item.section_title,
                "ordinal": item.ordinal,
                "content": item.content,
                "citation_markers": list(item.citation_markers),
                "citation_positions": [
                    {"marker_id": marker, "paragraph_index": paragraph_index,
                     "char_offset": char_offset}
                    for marker, paragraph_index, char_offset in item.citation_positions
                ],
                "content_sha256": item.content_hash,
            }
            for item in document.passages
        ],
    }
    derivative_bytes = json.dumps(derivative, ensure_ascii=False).encode()
    files = {
        "snapshots/wikidata/Q163872/entity.json": entity_bytes,
        "snapshots/wikipedia/Q163872/article.html": html,
        "snapshots/wikipedia-passages/Q163872/passages.json": derivative_bytes,
    }
    for relative, payload in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    manifest = {
        "schema": "cinegraph.catalog-pilot-capture/v1",
        "selection_sha256": "a" * 64,
        "run_status": "complete",
        "films": [{
            "title": "The Dark Knight",
            "year": 2008,
            "qid": "Q163872",
            "enwiki_title": "The Dark Knight",
            "wikidata_snapshot_path": "snapshots/wikidata/Q163872/entity.json",
            "wikidata_sha256": sha256(entity_bytes).hexdigest(),
            "wikidata_revision": 1,
            "wikipedia_snapshot_path": "snapshots/wikipedia/Q163872/article.html",
            "wikipedia_sha256": sha256(html).hexdigest(),
            "wikipedia_capture_url": article_url,
            "wikipedia_revision": document.metadata.revision_id,
            "wikipedia_title_resolved": "The Dark Knight",
            "passage_derivative_path": "snapshots/wikipedia-passages/Q163872/passages.json",
            "passage_derivative_sha256": sha256(derivative_bytes).hexdigest(),
        }],
    }
    (tmp_path / "capture-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = audit_capture_bundle(tmp_path)

    assert report["identity_and_capture_pass"] is True, report["failures"]
    assert report["schema"] == "cinegraph.catalog-pilot-audit/v4"
    assert report["total_passages"] == 3
    assert report["exact_duplicate_passages"] == 0
    assert report["wikidata_metadata_coverage"]["director"] == {
        "films_with_value": 1, "value_statements": 1,
    }
    assert report["cast_credit_statements"] == 2
    assert report["cast_credits_with_character_qualifier"] == 1
    assert report["passage_length_flags"] == [
        flag for film in report["films"] for flag in film["passage_length_flags"]
    ]
    assert all({"section_locator", "ordinal", "character_count", "content_sha256", "kind"} <= flag.keys()
               for flag in report["passage_length_flags"])
    assert section_categories({"Plot": 1, "Production / Development": 1})["production"] == 1
    assert section_categories({"Synopsis": 1, "Synopsis / Act I": 4})["plot"] == 5
    assert section_categories({"Story": 2})["plot"] == 2
    rendered = render_audit_markdown(report)
    assert "Source identity, snapshot hashes, and deterministic extraction: PASS" in rendered
    assert rendered.count("## Source policy and interpretation") == 1
    assert "## Structured Wikidata field coverage" in rendered
    if report["passage_length_flags"]:
        assert "## Passage length review flags" in rendered


def test_missing_article_sections_are_content_gaps_not_integrity_failures() -> None:
    assert missing_content_categories({"plot": 0, "production": 2}) == ["plot"]
    assert missing_content_categories({"plot": 1, "production": 2}) == []


def test_catalog_pilot_audit_reports_source_hash_mismatch(tmp_path: Path) -> None:
    manifest = {
        "schema": "cinegraph.catalog-pilot-capture/v1",
        "selection_sha256": "b" * 64,
        "run_status": "complete",
        "films": [{
            "title": "Fixture Film",
            "qid": "Q1",
            "wikidata_snapshot_path": "missing.json",
            "wikidata_sha256": "c" * 64,
        }],
    }
    (tmp_path / "capture-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = audit_capture_bundle(tmp_path)

    assert report["identity_and_capture_pass"] is False
    assert "Fixture Film (Q1)" in report["failures"][0]
