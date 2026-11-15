import hashlib
from pathlib import Path

import pytest

from scripts.bind_wikipedia_capture_prior import bind


def test_binding_preserves_review_state_and_rejects_source_or_identity_mismatch():
    payload = (Path(__file__).parent / "fixtures" / "wikipedia-article-html-slice-v1.html").read_bytes()
    manifest = {"schema": "cinegraph.wikipedia-review-capture/v1", "status": 200,
                "identity_status": "review_required", "rights_status": "review_required", "product_ingested": False,
                "sha256": hashlib.sha256(payload).hexdigest(), "byte_size": len(payload),
                "canonical_url": "https://en.wikipedia.org/wiki/The_Dark_Knight",
                "metadata": {"page_id": 4276475, "revision_id": 1383150687, "title": "The Dark Knight"}}
    row = {"wikidata_id": "Q163872", "wikipedia_page_id": "enwiki:4276475",
           "wikipedia_snapshot_id": "prior", "wikipedia_sha256": "oldhash", "wikipedia_revision": "1"}
    result = bind(manifest, row, payload)
    assert result["prior_snapshot_id"] == "prior" and result["rights_status"] == "review_required"
    with pytest.raises(ValueError):
        bind(manifest, {**row, "wikipedia_page_id": "enwiki:1"}, payload)
    with pytest.raises(ValueError):
        bind(manifest, row, payload + b"tampered")
