import pytest

from scripts.prepare_writer_refresh_manifest import manifest_for_capture


def capture():
    return {"status": "review_candidate", "metadata": {"wikidata_id": "Q1"}, "sha256": "a" * 64,
            "byte_size": 100, "requested_url": "https://en.wikipedia.org/wiki/Example",
            "canonical_url": "https://en.wikipedia.org/wiki/Example", "media_type": "text/html",
            "retrieved_at": "2026-11-15T00:00:00Z", "robots_sha256": "b" * 64,
            "sections": ["plot"], "prior_snapshot_id": "prior", "prior_sha256": "c" * 64,
            "prior_revision": "1"}


def test_manifest_remains_review_only_and_preserves_both_source_bindings():
    row = capture()
    row["storage_encoding"] = "gzip"
    result = manifest_for_capture("Q1", row)
    assert result["identity_status"] == result["rights_status"] == "review_required"
    assert result["product_ingested"] is False
    assert result["storage_encoding"] == "gzip"
    assert result["prior_sha256"] == "c" * 64
    assert result["sha256"] == "a" * 64


def test_manifest_rejects_mismatch_quarantine_and_unsafe_identity():
    with pytest.raises(ValueError):
        manifest_for_capture("Q2", capture())
    row = capture()
    row["status"] = "quarantined"
    with pytest.raises(ValueError):
        manifest_for_capture("Q1", row)
    with pytest.raises(ValueError):
        manifest_for_capture("../Q1", capture())
