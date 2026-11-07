import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_wikipedia_cast_candidates.py"
SPEC = importlib.util.spec_from_file_location("prepare_wikipedia_cast_candidates", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _manifests():
    capture = {
        "selection_sha256": "a" * 64,
        "films": [{
            "qid": "Q10", "wikipedia_sha256": "b" * 64,
            "wikipedia_revision": 123, "wikipedia_attribution_url": "https://en.wikipedia.org/wiki/Film",
            "capture_status": "complete", "wikipedia_status": "captured",
        }],
    }
    extraction = {
        "schema": "cinegraph.catalog-pilot-extraction/v1",
        "selection_sha256": "a" * 64,
        "films": [{
            "qid": "Q10", "source_snapshot_sha256": "b" * 64,
            "source_revision": 123, "canonical_url": "https://en.wikipedia.org/wiki/Film",
            "parser_version": "enwiki-article-html-extraction-v6",
            "passage_derivative_path": "snapshots/passages.json",
            "passage_derivative_sha256": "c" * 64,
        }],
    }
    return capture, extraction


def test_v6_extraction_binding_keeps_exact_source_and_derivative_identity():
    capture, extraction = _manifests()

    [bound] = MODULE._bind_extraction_manifest(capture, extraction)

    assert bound["passage_derivative_path"] == "snapshots/passages.json"
    assert bound["passage_derivative_sha256"] == "c" * 64
    assert bound["wikipedia_sha256"] == "b" * 64


@pytest.mark.parametrize("schema", [
    "cinegraph.wikipedia-passage-extraction/v6",
    "cinegraph.wikipedia-passage-extraction/6",
])
def test_v6_passage_derivatives_accept_both_immutable_schema_markers(schema):
    capture, _ = _manifests()
    film = capture["films"][0]
    binding = MODULE._passage_derivative_binding({
        "schema": schema,
        "parser_version": "enwiki-article-html-extraction-v6",
        "source_revision": 123,
        "source_snapshot_sha256": "b" * 64,
    }, film)

    assert all(binding.values())


@pytest.mark.parametrize("field,value", [
    ("source_snapshot_sha256", "d" * 64),
    ("source_revision", 124),
    ("canonical_url", "https://en.wikipedia.org/wiki/Other_film"),
    ("parser_version", "enwiki-article-html-extraction-v5"),
])
def test_extraction_binding_rejects_revision_url_hash_or_parser_mismatch(field, value):
    capture, extraction = _manifests()
    extraction["films"][0][field] = value

    with pytest.raises(ValueError, match="not bound"):
        MODULE._bind_extraction_manifest(capture, extraction)


def test_extraction_binding_rejects_a_different_selection_or_film_set():
    capture, extraction = _manifests()
    extraction["selection_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="different selections"):
        MODULE._bind_extraction_manifest(capture, extraction)

    capture, extraction = _manifests()
    extraction["films"].append(dict(extraction["films"][0]))
    with pytest.raises(ValueError, match="identities differ"):
        MODULE._bind_extraction_manifest(capture, extraction)
