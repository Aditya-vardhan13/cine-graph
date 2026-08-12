import json

from app.services.english_reference_shelf import Candidate
from app.services.reference_manifest import payload, write_manifest


def test_selection_manifest_is_explicit_about_its_non_imdb_source(tmp_path) -> None:
    document = payload([Candidate("Q1", 50), Candidate("Q2", 40)], 2000, 2025)
    path, digest = write_manifest(document, tmp_path / "evaluation.json")

    saved = json.loads(path.read_text())
    assert saved["schema"] == "cinegraph.selection-manifest/v1"
    assert "not IMDb" in saved["not_a_claim"]
    assert [entry["wikidata_id"] for entry in saved["entries"]] == ["Q1", "Q2"]
    assert len(digest) == 64
