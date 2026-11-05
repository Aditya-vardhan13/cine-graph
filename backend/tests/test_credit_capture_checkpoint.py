import json

from scripts.capture_credit_targets import save_checkpoint


def test_checkpoint_replacement_is_complete_and_replayable(tmp_path) -> None:
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, {"manifest_sha256": "abc", "captured": {}})
    save_checkpoint(path, {"manifest_sha256": "abc", "captured": {"Q1": {"sha256": "x"}}})
    assert json.loads(path.read_text())["captured"] == {"Q1": {"sha256": "x"}}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["checkpoint.json"]
