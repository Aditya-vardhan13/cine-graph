import importlib.util
from pathlib import Path
import json
import pytest

spec = importlib.util.spec_from_file_location("recovery_export",
    Path(__file__).resolve().parents[2] / "scripts/export_recovery_dataset.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_development_and_holdout_queries_remain_separate_and_unlabelled():
    design = json.loads((Path(__file__).parent / "fixtures/recovery-question-design-v1.json").read_text())
    splits = module.split_cases(design)
    assert len(splits["development"]) == 30
    assert len(splits["question_holdout"]) == 20
    assert not ({c["case_id"] for c in splits["development"]} &
                {c["case_id"] for c in splits["question_holdout"]})
    assert all(c["source_labels_status"] == "pending" for rows in splits.values() for c in rows)
    design["pairs"].append(design["pairs"][0])
    with pytest.raises(ValueError):
        module.split_cases(design)
