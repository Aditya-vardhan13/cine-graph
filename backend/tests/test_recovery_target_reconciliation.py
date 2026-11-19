import importlib.util
import hashlib
import json
from pathlib import Path
import pytest
from app.services.corpus_build_manifest import finalize_manifest

spec = importlib.util.spec_from_file_location(
    "recovery_target", Path(__file__).resolve().parents[2] / "scripts/reconcile_recovery_target.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs():
    raw = b"Series_Title,Released_Year\n Film ,2000\nExtra,2001\n"
    target = json.dumps({"input_sha256": hashlib.sha256(raw).hexdigest(),
        "candidates": [{"selection_rank": 1, "title": "Film", "release_year_candidate": 2000}]}).encode()
    coverage = json.dumps({"input_sha256": {"target": hashlib.sha256(target).hexdigest()},
        "films": [{"selection_rank": 1, "wikidata_id": "Q1", "mapping_status": "candidate_review_required"}]}).encode()
    build = json.dumps(finalize_manifest("c", [{"entity_id": "e", "title": "Film", "wikidata_id": "Q1",
        "build_eligible": False, "sources": []}])).encode()
    return raw, target, coverage, build


def test_reconciliation_preserves_unreviewed_identity_and_extra_rows():
    result = module.reconcile(*inputs())
    assert result["identity_approved"] == 0
    assert result["statuses"] == {"current_candidate": 1}
    assert result["csv_rows_outside_frozen_target"] == 1
    assert result["target_rows_with_eligible_candidate"] == 0


def test_reconciliation_refuses_drift_and_tampered_build():
    raw, target, coverage, build = inputs()
    with pytest.raises(ValueError, match="csv_target"):
        module.reconcile(raw+b"Other,2002\n", target, coverage, build)
    tampered = json.loads(build)
    tampered["films"][0]["build_eligible"] = True
    with pytest.raises(ValueError, match="build_manifest"):
        module.reconcile(raw, target, coverage, json.dumps(tampered).encode())
