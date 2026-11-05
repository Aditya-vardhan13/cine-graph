import json
from pathlib import Path

import pytest

from app.services.pair_relevance_eval import (
    merge_candidate_captures, reciprocal_rank_fusion, score, validate_manifest,
    validate_retrieval_candidate_limit,
)
from app.services.pair_reranker_trial import (
    require_disk_headroom, reranked_options, reranker_query, resume_rows,
)
from app.services.pair_relevance_review import labels_from_pair_sequences, packet_fingerprint, review_items


FIXTURE = Path(__file__).parent / "fixtures" / "pair-relevance-50-v1.json"


def test_pair_manifest_has_fifty_distinct_questions() -> None:
    manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    assert len(manifest["pairs"]) == 10
    assert sum(len(pair["questions"]) for pair in manifest["pairs"]) == 50


def test_retrieval_candidate_limit_is_bounded_by_supported_search_contract() -> None:
    validate_retrieval_candidate_limit(10)
    validate_retrieval_candidate_limit(200)
    with pytest.raises(ValueError, match="between 10 and 200"):
        validate_retrieval_candidate_limit(9)
    with pytest.raises(ValueError, match="between 10 and 200"):
        validate_retrieval_candidate_limit(201)


def test_review_score_requires_every_top_passage_label() -> None:
    cases = [
        {"case_id": f"P01-Q{i}", "film_qids": ["Q1", "Q2"],
         "question": f"Question {i}",
         "first_options": [{"chunk_id": f"a{i}"}], "second_options": [{"chunk_id": f"b{i}"}],
         "first_pool": [{"chunk_id": f"a{i}"}], "second_pool": [{"chunk_id": f"b{i}"}]}
        for i in range(1, 51)
    ]
    capture = {"cases": cases}
    with pytest.raises(ValueError, match="Missing 0/1"):
        score(capture, {})

    labels = {
        f"P01-Q{i}|{qid}|{chunk}": int(i <= 40)
        for i in range(1, 51)
        for qid, chunk in (("Q1", f"a{i}"), ("Q2", f"b{i}"))
    }
    metrics = score(capture, labels)
    assert metrics["side_precision_at_1"] == 0.8
    assert metrics["pair_success_at_1"] == 0.8
    assert metrics["passed_80_percent_pair_gate"] is True
    reranking = {"complete": True, "cases": [
        {"case_id": case["case_id"],
         "question": case["question"], "film_qids": case["film_qids"],
         "first_ranking": case["first_options"], "second_ranking": case["second_options"]}
        for case in cases
    ]}
    assert score(capture, labels, reranking=reranking)["pair_success_at_1"] == 0.8
    reranking["complete"] = False
    with pytest.raises(ValueError, match="same complete"):
        score(capture, labels, reranking=reranking)
    reranking["complete"] = True
    reranking["cases"][0]["first_ranking"] = [{"chunk_id": "stale"}]
    with pytest.raises(ValueError, match="candidate pool differs"):
        score(capture, labels, reranking=reranking)


def test_reranker_orders_source_chunk_ids_without_rewriting_evidence() -> None:
    pool = [{"chunk_id": "a", "section_title": "Plot"},
            {"chunk_id": "b", "section_title": "Production"}]
    assert [item["chunk_id"] for item in reranked_options(pool, [0.1, 0.9])] == ["b", "a"]
    with pytest.raises(ValueError, match="every candidate"):
        reranked_options(pool, [0.1])


def test_reciprocal_rank_fusion_uses_candidate_pool_and_stable_tie_breaking() -> None:
    case = {"case_id": "P01-Q1", "question": "Q?", "film_qids": ["Q1", "Q2"],
            "first_pool": [{"chunk_id": "a"}, {"chunk_id": "b"}],
            "second_pool": [{"chunk_id": "c"}, {"chunk_id": "d"}]}
    capture = {"cases": [case]}
    rankings = [
        {"complete": True, "cases": [{"case_id": "P01-Q1", "question": "Q?",
         "film_qids": ["Q1", "Q2"], "first_ranking": [{"chunk_id": "a"}, {"chunk_id": "b"}],
         "second_ranking": [{"chunk_id": "c"}, {"chunk_id": "d"}]}]},
        {"complete": True, "cases": [{"case_id": "P01-Q1", "question": "Q?",
         "film_qids": ["Q1", "Q2"], "first_ranking": [{"chunk_id": "b"}, {"chunk_id": "a"}],
         "second_ranking": [{"chunk_id": "d"}, {"chunk_id": "c"}]}]},
    ]
    result = reciprocal_rank_fusion(capture, rankings, constant=1)
    assert [item["chunk_id"] for item in result["cases"][0]["first_ranking"]] == ["a", "b"]
    assert [item["chunk_id"] for item in result["cases"][0]["second_ranking"]] == ["c", "d"]
    with pytest.raises(ValueError, match="at least one ranking"):
        reciprocal_rank_fusion(capture, [])


def test_candidate_capture_union_preserves_provenance_and_rejects_changed_source() -> None:
    def capture(method: str, extra_chunk: str) -> dict:
        cases = []
        for index in range(1, 51):
            cases.append({
                "case_id": f"P01-Q{index}", "pair_id": "P01",
                "film_qids": ["Q1", "Q2"], "titles": ["One", "Two"],
                "question": f"Question {index}",
                "first_options": [{"chunk_id": f"a{index}"}], "second_options": [],
                "first_pool": [
                    {"chunk_id": f"a{index}", "content": "same source passage"},
                    {"chunk_id": extra_chunk, "content": (
                        "same extra source" if extra_chunk == "shared" else f"from {method}"
                    )},
                ], "second_pool": [],
            })
        return {"manifest_version": "v1", "method": method, "cases": cases}

    merged = merge_candidate_captures(capture("hybrid", "shared"), capture("lexical", "shared"))
    assert merged["method"] == "candidate-union"
    assert merged["source_methods"] == ["hybrid", "lexical"]
    assert merged["cases"][0]["first_pool"][0]["retrieval_sources"] == ["hybrid", "lexical"]
    assert len(merged["cases"][0]["first_pool"]) == 2

    changed = capture("lexical", "shared")
    changed["cases"][0]["first_pool"][0]["content"] = "changed passage"
    with pytest.raises(ValueError, match="Source passage changed"):
        merge_candidate_captures(capture("hybrid", "shared"), changed)


def test_reranker_query_can_make_scoped_film_identity_explicit() -> None:
    question = "How does the protagonist change?"
    assert reranker_query(question) == question
    assert reranker_query(question, "Her") == f"Film: Her\nResearch question: {question}"


def test_review_packet_blinds_model_identity_and_deduplicates_chunks() -> None:
    cases = [
        {"case_id": f"P01-Q{i}", "film_qids": ["Q1", "Q2"], "titles": ["One", "Two"],
         "question": f"Question {i}",
         "first_options": [{"chunk_id": "a"}], "second_options": [{"chunk_id": "b"}],
         "first_pool": [{"chunk_id": "a", "section_title": "Plot", "content": "A"},
                        {"chunk_id": "c", "section_title": "Plot", "content": "C"}],
         "second_pool": [{"chunk_id": "b", "section_title": "Plot", "content": "B"}],
         }
        for i in range(1, 51)
    ]
    ranking = {"complete": True, "cases": [
        {"case_id": case["case_id"], "question": case["question"],
         "film_qids": case["film_qids"],
         "first_ranking": [{"chunk_id": "c"}, {"chunk_id": "a"}],
         "second_ranking": [{"chunk_id": "b"}]} for case in cases
    ]}
    packet = review_items({"cases": cases}, [ranking])
    assert len(packet) == 150
    assert {item["passage"] for item in packet[:3]} == {"A", "B", "C"}
    assert all("ranking" not in item and "score" not in item for item in packet)
    lengths = {f"P01": len(packet)}
    reviewed = labels_from_pair_sequences(packet, {
        "fingerprint": packet_fingerprint(packet),
        "pairs": {pair: "1" * count for pair, count in lengths.items()},
    })
    assert len(reviewed) == 150
    with pytest.raises(ValueError, match="exact review packet"):
        labels_from_pair_sequences(packet, {"fingerprint": "wrong", "pairs": {}})


def test_reranker_resume_requires_same_question_and_candidate_pool(tmp_path: Path) -> None:
    capture = {"cases": [{"case_id": "P01-Q1", "question": "A?", "film_qids": ["Q1", "Q2"],
                          "first_pool": [{"chunk_id": "a"}],
                          "second_pool": [{"chunk_id": "b"}]}]}
    row = {"case_id": "P01-Q1", "question": "A?", "film_qids": ["Q1", "Q2"],
           "first_ranking": [{"chunk_id": "a"}], "second_ranking": [{"chunk_id": "b"}]}
    output = tmp_path / "checkpoint.json"
    output.write_text(json.dumps({"capture": "capture.json", "model": "test-model",
                                  "instruction": "test", "cases": [row]}), encoding="utf-8")
    assert resume_rows(output, capture_path=Path("capture.json"), capture=capture,
                       model_name="test-model", instruction="test", enabled=True) == [row]
    capture["cases"][0]["first_pool"][0]["chunk_id"] = "changed"
    with pytest.raises(ValueError, match="different candidate pool"):
        resume_rows(output, capture_path=Path("capture.json"), capture=capture,
                    model_name="test-model", instruction="test", enabled=True)


def test_local_trial_refuses_low_disk_headroom_without_mocks(tmp_path: Path) -> None:
    require_disk_headroom(tmp_path / "checkpoint.json", min_free_gb=0)
    with pytest.raises(RuntimeError, match="before continuing"):
        require_disk_headroom(tmp_path / "checkpoint.json", min_free_gb=1_000_000)
