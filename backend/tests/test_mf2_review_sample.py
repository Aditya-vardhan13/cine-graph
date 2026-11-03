import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("mf2_review_sample", Path(__file__).resolve().parents[2] / "scripts/build_mf2_review_sample.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_sampling_is_deterministic_and_preserves_all_ranked_leads():
    passage = {"document_id": "mf2:1:synopsis", "start": 0, "end": 7, "content": "A story"}
    lead = {"passage_id": "p", "document_id": passage["document_id"], "start": 0, "end": 7, "score": 1.0}
    rows = [{"case_id": f"mf2:1:{i}:a", "claim": "A claim", "ranked": [lead] * 6,
             "evidence_document_ids": ["mf2:1:synopsis"]} for i in range(3)]
    sample, films = module.select_review_cases(rows, {"p": passage})
    reversed_sample, _ = module.select_review_cases(list(reversed(rows)), {"p": passage})
    assert films == 1 and len(sample) == 2
    assert [r["case_id"] for r in sample] == [r["case_id"] for r in reversed_sample]
    assert all(len(r["leads"]) == 6 and r["review_status"] == "not-reviewed" for r in sample)


def test_sampling_rejects_changed_source_offsets():
    row = {"case_id": "x", "claim": "A claim", "evidence_document_ids": ["mf2:1:synopsis"],
           "ranked": [{"passage_id": "p", "document_id": "mf2:1:synopsis", "start": 1, "end": 7}]}
    passage = {"document_id": "mf2:1:synopsis", "start": 0, "end": 7, "content": "A story"}
    with pytest.raises(ValueError, match="provenance"):
        module.select_review_cases([row], {"p": passage})
