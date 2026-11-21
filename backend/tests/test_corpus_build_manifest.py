from copy import deepcopy
import pytest
from app.services.corpus_build_manifest import finalize_manifest, manifest_source


def source(**changes):
    data = dict(snapshot_id="s", snapshot_hash="a"*64, source_url="https://example.org/film",
        revision="1", fetch_status="success", integrity="verified", semantic_approved=True,
        passages=[{"id": "p", "section": "plot", "ordinal": 0, "hash_verified": True}])
    return manifest_source(**{**data, **changes})


def test_admission_requires_bytes_permission_and_passage_integrity():
    assert source()["build_eligible"]
    for changes in ({"integrity": "missing"}, {"fetch_status": "failed"},
                    {"fetch_status": None}, {"semantic_approved": False},
                    {"passages": []}, {"passages": [{"id": "p", "section": "plot",
                     "ordinal": 0, "hash_verified": False}]}):
        assert not source(**changes)["build_eligible"]


def test_manifest_hash_is_stable_and_binds_content_not_input_order():
    films = [{"entity_id": "b", "sources": [source()]}, {"entity_id": "a", "sources": []}]
    manifest = finalize_manifest("collection", films)
    assert manifest == finalize_manifest("collection", list(reversed(films)))
    altered = deepcopy(films)
    altered[0]["sources"][0]["revision"] = "2"
    assert manifest["manifest_sha256"] != finalize_manifest("collection", altered)["manifest_sha256"]
    assert not manifest["identity_review_performed"]
    with pytest.raises(ValueError, match="duplicate"):
        finalize_manifest("collection", [films[0], films[0]])
