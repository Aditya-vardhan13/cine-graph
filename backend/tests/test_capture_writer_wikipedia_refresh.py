import hashlib

import pytest

from scripts.capture_credit_targets import save_checkpoint
from scripts.capture_writer_wikipedia_refresh import SCHEMA, targets, verified_checkpoint


def test_only_mechanically_consistent_rows_become_review_candidates():
    audit = {"schema": "cinegraph.writer-source-identity-audit/v1", "review_status": "review_required",
             "entries": [{"wikidata_id": "Q1", "wikipedia_page_id": "enwiki:1", "mechanical_checks_passed": True},
                         {"wikidata_id": "Q2", "wikipedia_page_id": "enwiki:2", "mechanical_checks_passed": False}]}
    assert [row["wikidata_id"] for row in targets(audit)] == ["Q1"]
    audit["entries"].append(dict(audit["entries"][0]))
    with pytest.raises(ValueError, match="duplicate"):
        targets(audit)


def test_checkpoint_resume_requires_exact_audit_and_retained_bytes(tmp_path):
    payload = b"retained HTML"
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / "snapshots").mkdir()
    path = tmp_path / "snapshots" / f"{digest}.html"
    path.write_bytes(payload)
    save_checkpoint(tmp_path / "checkpoint.json", {"schema": SCHEMA, "audit_sha256": "pinned",
                                                  "captures": {"Q1": {"sha256": digest, "status": "review_candidate"}}})
    assert "Q1" in verified_checkpoint(tmp_path, "pinned", {"Q1"})["captures"]
    with pytest.raises(ValueError, match="pinned audit"):
        verified_checkpoint(tmp_path, "other", {"Q1"})
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="missing or altered"):
        verified_checkpoint(tmp_path, "pinned", {"Q1"})
