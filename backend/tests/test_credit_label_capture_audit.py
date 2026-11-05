import hashlib
import json

import pytest

from app.services.credit_label_capture_audit import audit_credit_label_capture


def _write_bundle(root):
    manifest_path = root / "credit-targets-v1.json"
    manifest = {
        "schema": "cinegraph.credit-target-manifest/v1",
        "films": 1,
        "targets": [
            {"qid": "Q1", "references": [{"film_qid": "Q10", "role": "cast"}]},
            {"qid": "Q2", "references": [{"film_qid": "Q10", "role": "character", "person_qid": "Q1"}]},
        ],
    }
    manifest_bytes = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode()
    manifest_path.write_bytes(manifest_bytes)
    capture_dir = root / "capture"
    captured = {}
    for qid, label in (("Q1", "Actor Name"), ("Q2", "Character Name")):
        payload = (json.dumps({"entities": {qid: {
            "id": qid, "lastrevid": 11, "labels": {"en": {"language": "en", "value": label}},
        }}}, sort_keys=True) + "\n").encode()
        digest = hashlib.sha256(payload).hexdigest()
        relative = f"snapshots/{qid}/{digest}.json"
        target = capture_dir / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(payload)
        captured[qid] = {
            "source_url": f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json",
            "source_revision": 11,
            "robots_sha256": "a" * 64,
            "sha256": digest,
            "snapshot_path": relative,
            "english_label": label,
        }
    (capture_dir / "checkpoint.json").write_text(json.dumps({
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "captured": captured,
    }))
    return manifest_path, capture_dir


def test_completed_capture_audits_source_integrity_and_named_credit_coverage(tmp_path):
    manifest, capture = _write_bundle(tmp_path)

    report = audit_credit_label_capture(manifest, capture)

    assert report["status"] == "complete"
    assert report["targets"] == report["captured"] == report["with_english_label"] == 2
    assert report["films_with_named_cast"] == report["films_with_named_character_candidates"] == 1
    assert report["robots_sha256_count"] == 1


def test_capture_audit_rejects_payload_tampering(tmp_path):
    manifest, capture = _write_bundle(tmp_path)
    checkpoint = json.loads((capture / "checkpoint.json").read_text())
    item = checkpoint["captured"]["Q1"]
    target = capture / item["snapshot_path"]
    target.write_bytes(b"{}")

    with pytest.raises(ValueError, match="Snapshot hash mismatch"):
        audit_credit_label_capture(manifest, capture)


def test_capture_audit_rejects_incomplete_manifest_binding(tmp_path):
    manifest, capture = _write_bundle(tmp_path)
    checkpoint_path = capture / "checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text())
    checkpoint["captured"].pop("Q2")
    checkpoint_path.write_text(json.dumps(checkpoint))

    with pytest.raises(ValueError, match="incomplete"):
        audit_credit_label_capture(manifest, capture)
