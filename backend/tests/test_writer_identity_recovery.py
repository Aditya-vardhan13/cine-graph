import hashlib
import json

import pytest

from scripts.audit_writer_identity_recovery import audit_recovery
from scripts.capture_writer_identity_recovery import local_output, recovery_targets


def test_recovery_selects_only_unavailable_wikidata_without_approving():
    report = {"schema": "cinegraph.writer-source-identity-audit/v1", "review_status": "review_required",
              "entries": [{"wikidata_id": "Q123", "issues": ["wikidata_snapshot_unavailable"]},
                          {"wikidata_id": "Q456", "issues": []}]}
    assert [item["wikidata_id"] for item in recovery_targets(report)] == ["Q123"]
    report["entries"].append({"wikidata_id": "Q123", "issues": ["wikidata_snapshot_unavailable"]})
    with pytest.raises(ValueError, match="unique valid"):
        recovery_targets(report)


def test_recovery_output_must_stay_in_local_evaluation_data(tmp_path):
    with pytest.raises(ValueError, match="data/evaluation"):
        local_output(tmp_path / "elsewhere")


def test_recovery_audit_checks_exact_payload_and_keeps_review_required(tmp_path):
    target = {"wikidata_id": "Q123", "film_title": "Fixture", "issues": ["wikidata_snapshot_unavailable"],
              "wikipedia_url": "https://en.wikipedia.org/wiki/Fixture", "wikidata_snapshot_id": "old",
              "wikidata_revision": "1", "wikidata_sha256": "a" * 64}
    source_audit = {"schema": "cinegraph.writer-source-identity-audit/v1", "review_status": "review_required",
                    "entries": [target]}
    audit_path = tmp_path / "audit.json"
    audit_path.write_text(json.dumps(source_audit), encoding="utf-8")
    source = {"entities": {"Q123": {"id": "Q123", "lastrevid": 2,
                                  "sitelinks": {"enwiki": {"title": "Fixture"}}}}}
    payload = json.dumps(source).encode()
    recovery = tmp_path / "recovery"
    recovery.mkdir()
    (recovery / "capture.json").write_bytes(payload)
    checkpoint = {"schema": "cinegraph.writer-identity-recovery/v1",
                  "audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
                  "captures": {"Q123": {"snapshot_path": "capture.json", "sha256": hashlib.sha256(payload).hexdigest(),
                      "source_url": "https://www.wikidata.org/wiki/Special:EntityData/Q123.json",
                      "source_revision": 2, "robots_sha256": "b" * 64, "identity_status": "review_required",
                      "product_ingested": False, "previous_snapshot_id": "old", "previous_revision": "1",
                      "previous_sha256": "a" * 64, "wikipedia_title": "Fixture", "new_sitelink_title": "Fixture"}}}
    (recovery / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    result = audit_recovery(audit_path, recovery)
    assert result["complete"] and result["counts"]["mechanical_pass"] == 1
    assert result["entries"][0]["identity_status"] == "review_required"
    (recovery / "capture.json").write_bytes(b"corrupted")
    result = audit_recovery(audit_path, recovery)
    assert result["counts"]["mechanical_pass"] == 0
    assert result["entries"][0]["issues"]
