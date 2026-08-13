import json

from app.services.selection_reconciliation import reconcile


def test_reconciliation_retains_seed_values_and_canonical_identity(tmp_path) -> None:
    manifest = tmp_path / "seed.json"
    manifest.write_text(json.dumps({
        "schema": "cinegraph.user-selection-manifest/v1",
        "entries": [{"position": 4, "title": "Original", "release_year": 2014}],
    }), encoding="utf-8")
    corrections = tmp_path / "corrections.json"
    corrections.write_text(json.dumps({
        "schema": "cinegraph.selection-reconciliation/v1",
        "corrections": [{
            "position": 4, "title": "Canonical", "release_year": 2004,
            "wikidata_id": "Q4", "wikipedia_title": "Canonical (film)",
            "evidence_url": "https://example.test/Q4", "reason": "translated title",
        }],
    }), encoding="utf-8")

    result = reconcile(manifest, corrections)

    assert result["reconciliation"]["corrections_applied"] == 1
    assert result["entries"] == [{
        "position": 4, "title": "Canonical", "release_year": 2004,
        "seed_title": "Original", "seed_release_year": 2014,
        "wikidata_id": "Q4", "wikipedia_title": "Canonical (film)",
        "selection_reconciliation": {
            "reason": "translated title", "evidence_url": "https://example.test/Q4",
        },
    }]
