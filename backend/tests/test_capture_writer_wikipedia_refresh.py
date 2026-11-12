import hashlib
from pathlib import Path

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
    payload = (Path(__file__).parent / "fixtures" / "wikipedia-article-html-slice-v1.html").read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / "snapshots").mkdir()
    path = tmp_path / "snapshots" / f"{digest}.html"
    path.write_bytes(payload)
    target = {"wikipedia_snapshot_id": "old", "wikipedia_sha256": "oldhash", "wikipedia_revision": "1",
              "wikipedia_url": "https://en.wikipedia.org/wiki/The_Dark_Knight", "wikipedia_page_id": "enwiki:4276475"}
    capture = {"sha256": digest, "byte_size": len(payload), "status": "review_candidate", "issues": [],
               "canonical_url": target["wikipedia_url"], "prior_snapshot_id": "old", "prior_sha256": "oldhash",
               "prior_revision": "1", "requested_url": target["wikipedia_url"], "identity_status": "review_required",
               "rights_status": "review_required", "product_ingested": False,
               "metadata": {"title": "The Dark Knight", "page_id": 4276475, "wikidata_id": "Q163872", "revision_id": 1383150687},
               "sections": ["lead", "plot", "production/development"]}
    save_checkpoint(tmp_path / "checkpoint.json", {"schema": SCHEMA, "audit_sha256": "pinned",
                                                  "captures": {"Q163872": capture}})
    rows = {"Q163872": target}
    assert "Q163872" in verified_checkpoint(tmp_path, "pinned", rows)["captures"]
    with pytest.raises(ValueError, match="pinned audit"):
        verified_checkpoint(tmp_path, "other", rows)
    capture["metadata"]["page_id"] = 1
    save_checkpoint(tmp_path / "checkpoint.json", {"schema": SCHEMA, "audit_sha256": "pinned", "captures": {"Q163872": capture}})
    with pytest.raises(ValueError, match="metadata changed"):
        verified_checkpoint(tmp_path, "pinned", rows)
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="missing or altered"):
        verified_checkpoint(tmp_path, "pinned", rows)
