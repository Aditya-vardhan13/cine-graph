"""The blind canary must bind labels to passage content before revealing variants."""
from __future__ import annotations

from copy import deepcopy

import pytest

from app.services.pair_canary_review import make_packet, score


def _capture(version: str) -> dict:
    return {
        "case_count": 20,
        "method": "hybrid",
        "results": [
            {
                "case_id": f"P{index // 5 + 1:02d}-Q{index % 5 + 1}",
                "question": f"How does choice {index} change the story?",
                "sides": [
                    {
                        "film_qid": qid,
                        "restricted_top_three": [{
                            "source_snapshot_id": f"snapshot-{qid}",
                            "section_locator": "plot",
                            "content": f"{qid} evidence for question {index} in {version}",
                        }],
                        "whole_film_top_three": [{
                            "source_snapshot_id": f"snapshot-{qid}",
                            "section_locator": "production",
                            "content": f"{qid} additional evidence for question {index} in {version}",
                        }],
                    }
                    for qid in ("Q1", "Q2")
                ],
            }
            for index in range(20)
        ],
    }


def test_packet_is_blind_content_bound_and_scores_only_complete_reviews() -> None:
    packet, mapping = make_packet(_capture("v1"), _capture("v2"))
    assert len(packet["items"]) == 160
    assert "variant" not in packet["items"][0]
    labels = {
        "fingerprint": packet["fingerprint"],
        "labels": {
            item["key"]: {"support": "direct", "rationale": "The source addresses the choice."}
            for item in packet["items"]
        },
    }
    scored = score(packet, mapping, labels)
    assert scored["metrics"]["v2-whole-film"]["direct_pairs"] == 20
    assert scored["head_oracle"]["direct_pairs"] == 20
    incomplete = deepcopy(labels)
    incomplete["labels"].pop(packet["items"][0]["key"])
    with pytest.raises(ValueError, match="Every blinded passage"):
        score(packet, mapping, incomplete)
    changed = deepcopy(packet)
    changed["items"][0]["passage"] += " changed"
    with pytest.raises(ValueError, match="bind"):
        score(changed, mapping, labels)


def test_compact_review_requires_each_case_and_exact_passage_count() -> None:
    packet, mapping = make_packet(_capture("v1"), _capture("v2"))
    compact = {
        "fingerprint": packet["fingerprint"],
        "cases": {
            f"P{index // 5 + 1:02d}-Q{index % 5 + 1}": {
                "sequence": "DDDDDDDD",
                "rationale": "Each passage contains the requested choice.",
            }
            for index in range(20)
        },
    }
    assert score(packet, mapping, compact)["metrics"]["v1-restricted"]["direct_pairs"] == 20
    compact["cases"]["P01-Q1"]["sequence"] = "D"
    with pytest.raises(ValueError, match="Incomplete review sequence"):
        score(packet, mapping, compact)


def test_top_three_scores_candidate_recall_without_relabeling_heads() -> None:
    first, second = _capture("v1"), _capture("v2")
    for capture in (first, second):
        for case in capture["results"]:
            for side in case["sides"]:
                for field in ("restricted_top_three", "whole_film_top_three"):
                    head = side[field][0]
                    side[field] = [
                        {**head, "content": f"{head['content']} rank {rank}"}
                        for rank in (1, 2, 3)
                    ]
    packet, mapping = make_packet(first, second, depth=3)
    assert len(packet["items"]) == 480
    labels = {"fingerprint": packet["fingerprint"], "labels": {
        item["key"]: {
            "support": "direct" if item["passage"].endswith("rank 3") else "irrelevant",
            "rationale": "Only the third passage addresses the question.",
        }
        for item in packet["items"]
    }}
    scored = score(packet, mapping, labels)
    assert scored["metrics"]["v2-restricted"]["direct_pairs"] == 20
    assert scored["metrics"]["v2-restricted"]["pair_success_at_3"] == 1.0
    assert "pair_success_at_1" not in scored["metrics"]["v2-restricted"]
    assert "top-3" in scored["head_oracle"]["caution"]
    with pytest.raises(ValueError, match="review depths"):
        make_packet(first, second, depth=2)
