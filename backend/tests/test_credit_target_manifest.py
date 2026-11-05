from hashlib import sha256
import json
from pathlib import Path

import pytest

from app.services.credit_target_manifest import select_credit_target_qids, select_credit_targets, snak_qid


def test_snak_qid_requires_a_wikidata_value() -> None:
    assert snak_qid({"snaktype": "value", "datavalue": {"value": {"id": "Q45772"}}}) == "Q45772"
    assert snak_qid({"snaktype": "novalue"}) is None
    assert snak_qid({"snaktype": "value", "datavalue": {"value": {"id": "Q0"}}}) is None
    assert snak_qid(None) is None


def test_intake_target_selection_uses_explicit_people_and_character_links_only() -> None:
    def snak(qid: str) -> dict:
        return {"snaktype": "value", "datavalue": {"value": {"id": qid}}}

    entity = {"claims": {
        "P161": [{"rank": "normal", "mainsnak": snak("Q1"),
                  "qualifiers": {"P453": [snak("Q2"), snak("Q3")]}}],
        "P57": [{"rank": "normal", "mainsnak": snak("Q4")}],
        "P58": [{"rank": "deprecated", "mainsnak": snak("Q5")}],
    }}

    assert select_credit_target_qids(entity) == ["Q1", "Q2", "Q3", "Q4"]


def test_manifest_checks_snapshot_identity_and_hash(tmp_path: Path) -> None:
    fixture = Path(__file__).parent / "fixtures" / "wikidata-entitydata-response-slice-v1.json"
    payload = fixture.read_bytes()
    (tmp_path / "source.json").write_bytes(payload)
    capture = {"selection_sha256": "selection", "films": [{"qid": "Q5815826", "identity_status": "verified",
               "wikidata_status": "captured", "wikidata_snapshot_path": "source.json",
               "wikidata_sha256": sha256(payload).hexdigest(), "wikidata_revision": 2530451875}]}
    (tmp_path / "capture-manifest.json").write_text(json.dumps(capture))
    assert select_credit_targets(tmp_path)["films"] == 1
    assert select_credit_targets(tmp_path)["targets"] == []
    capture["films"][0]["wikidata_sha256"] = "incorrect"
    (tmp_path / "capture-manifest.json").write_text(json.dumps(capture))
    with pytest.raises(ValueError, match="hash mismatch"):
        select_credit_targets(tmp_path)
