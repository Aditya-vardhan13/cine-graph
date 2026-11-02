from copy import deepcopy
import json
import re
from types import SimpleNamespace

import pytest

from app.services.rag_dense_trial import digest
from app.services.rag_sentence_index import build_index
from app.services.rag_grounded_trial import (
    answer_schema, collect_generation, messages, pack_evidence, quote_spans, resolve_span_answer, select_cases, system_prompt, validate_answer,
)


def example():
    documents = [{"chunk_id": f"{film}{i}", "film_qid": film, "film_title": film,
                  "section_title": "Plot", "section_locator": "plot", "passage_ordinal": 3 - i,
                  "chunk_ordinal": 0, "source_snapshot_id": f"revision-{film}",
                  "content": "A specific choice brings a cost. The entire ending must remain visible."}
                 for film in ("A", "B") for i in range(3)]
    frozen = {"case_id": "C1", "film_qids": ["A", "B"], "question": "What does this choice cost?"}
    corpus = {"documents": documents, "cases": [frozen]}
    corpus["fingerprint"] = digest(corpus)
    case = {**frozen, "sides": [{"film_qid": film, "ranked": [{"chunk_id": f"{film}{i}"} for i in range(3)]}
                                 for film in ("A", "B")]}
    return corpus, case


def payload():
    reading = "This provisional reading identifies a specific choice and its personal cost."
    quote = "A specific choice brings a cost."
    return {"first": {"reading": reading, "support": [{"ref": "A1", "quote": quote}], "limit": "Interpretation needs review."},
            "second": {"reading": reading, "support": [{"ref": "B1", "quote": quote}], "limit": ""},
            "comparison": {"reading": reading, "support": [{"ref": f"{s}1", "quote": quote} for s in ("A", "B")], "limit": ""},
            "writing_move": "Write a scene where saving a colleague creates a different cost for the protagonist's family."}


def test_pack_preserves_full_source_both_sides_and_explicit_omissions():
    corpus, case = example()
    pack = pack_evidence(corpus, case, token_count=lambda text: 1, budget=4)
    assert [e["ref"] for e in pack["entries"]] == ["A1", "A2", "B1", "B2"]
    assert len(pack["omissions"]) == 2
    assert all(e["content"].endswith("ending must remain visible.") for e in pack["entries"])
    assert "A specific choice" in messages(pack)[1]["content"]
    source_order = pack_evidence(corpus, case, token_count=lambda text: 1, budget=4, order="source")
    assert {e["chunk_id"] for e in source_order["entries"]} == {e["chunk_id"] for e in pack["entries"]}
    assert [e["ref"] for e in source_order["entries"]] == ["A2", "A1", "B2", "B1"]


def test_pack_rejects_wrong_scope_changed_question_and_silent_window_expansion():
    corpus, case = example()
    for change in ("question", "wrong_film", "window"):
        wrong = deepcopy(case)
        if change == "question":
            wrong["question"] = "Different question"
        elif change == "wrong_film":
            wrong["sides"][0]["ranked"][0]["chunk_id"] = "B0"
        else:
            wrong["sides"][0]["ranked"][0]["start"] = 5
        with pytest.raises(ValueError):
            pack_evidence(corpus, wrong, token_count=lambda text: 1)
    with pytest.raises(ValueError, match="Each film"):
        pack_evidence(corpus, case, token_count=len, budget=1)


def test_citation_binding_rejects_invented_quotes_wrong_film_and_one_sided_contrast():
    corpus, case = example()
    pack = pack_evidence(corpus, case, token_count=len)
    assert validate_answer(json.dumps(payload()), pack)["first"]["support"][0]["ref"] == "A1"
    for field, value in (("ref", "B1"), ("ref", "A99"), ("quote", "A fabricated quote about this choice.")):
        draft = payload()
        draft["first"]["support"][0][field] = value
        with pytest.raises(ValueError):
            validate_answer(json.dumps(draft), pack)
    draft = payload()
    draft["comparison"]["support"].pop()
    with pytest.raises(ValueError, match="both films"):
        validate_answer(json.dumps(draft), pack)


def test_exact_quotation_is_not_treated_as_entailment_or_quality():
    corpus, case = example()
    pack = pack_evidence(corpus, case, token_count=len)
    draft = payload()
    draft["first"]["reading"] = "The moon is made of cheese and the source supposedly proves this claim."
    # Deliberate counterexample: source binding cannot establish semantic support.
    # A separate review MUST fail this, not report contract validity as accuracy.
    assert validate_answer(json.dumps(draft), pack)


def test_model_text_cut_off_by_schema_length_is_rejected():
    corpus, case = example()
    pack = pack_evidence(corpus, case, token_count=len)
    for field in ("first", "limit", "writing_move"):
        draft = payload()
        if field == "first":
            draft[field]["reading"] = draft[field]["reading"].rstrip(".")
        elif field == "limit":
            draft["first"]["limit"] = draft["first"]["limit"].rstrip(".")
        else:
            draft[field] = draft[field].rstrip(".")
        with pytest.raises(ValueError):
            validate_answer(json.dumps(draft), pack)


def test_predeclared_case_selection_preserves_frozen_order_and_rejects_unknowns():
    cases = [{"case_id": key} for key in ("A", "B", "C")]
    assert select_cases(cases, ["C", "A"]) == [cases[0], cases[2]]
    for selected in (["A", "A"], ["missing"]):
        with pytest.raises(ValueError):
            select_cases(cases, selected)
    assert system_prompt(span_ids=True, citation_first=True) != system_prompt(span_ids=True, citation_first=False)


def test_optional_sentence_citations_are_bound_to_the_exact_corpus():
    corpus, case = example()
    index = build_index(corpus, lambda text: [(0, len(text))], segmenter_version="fixture")
    pack = pack_evidence(corpus, case, token_count=len, sentence_index=index)
    spans = quote_spans(pack)
    assert spans["A1.S1"]["quote"] == pack["entries"][0]["content"]
    broken = deepcopy(index)
    broken["documents"][0]["spans"][0]["end"] -= 1
    with pytest.raises(ValueError, match="frozen corpus"):
        pack_evidence(corpus, case, token_count=len, sentence_index=broken)


def test_generation_stream_checks_space_and_preserves_complete_output():
    chunks = [SimpleNamespace(text=text, generation_tokens=i, finish_reason=None if i == 1 else "stop",
              generation_tps=10.0, prompt_tps=20.0) for i, text in ((1, "one "), (32, "two"))]
    checked = []
    text, stats = collect_generation(chunks, check_space=lambda: checked.append(True))
    assert text == "one two" and stats["finish_reason"] == "stop" and len(checked) == 2
    with pytest.raises(ValueError, match="no generation"):
        collect_generation([], check_space=lambda: None)
    def low_disk():
        raise RuntimeError("disk reserve")
    with pytest.raises(RuntimeError, match="disk reserve"):
        collect_generation(chunks, check_space=low_disk)


def test_span_ids_preserve_every_source_character_and_resolve_without_model_copying():
    corpus, case = example()
    pack = pack_evidence(corpus, case, token_count=len)
    original = {e["ref"]: e["content"] for e in pack["entries"]}
    encoded = json.loads(messages(pack, span_ids=True)[1]["content"])
    for entry in encoded["evidence"]:
        assert re.sub(r"\[[AB]\d+\.W\d+\] ", "", entry["text"]) == original[entry["ref"]]
    spans = quote_spans(pack)
    draft = payload()
    for field in ("first", "second", "comparison"):
        draft[field]["support"] = [{"ref": f"{item['ref']}.W1"} for item in draft[field]["support"]]
    answer = resolve_span_answer(json.dumps(draft), pack)
    assert answer["first"]["support"][0]["quote"] == spans["A1.W1"]["quote"]
    assert answer_schema(pack, span_ids=True)["properties"]["first"]["properties"]["support"]["items"]["properties"]["ref"]["enum"] == [k for k in spans if k.startswith("A")]
    comparison = answer_schema(pack, span_ids=True)["properties"]["comparison"]["properties"]["support"]
    assert comparison["minItems"] == comparison["maxItems"] == 2
    assert all(ref.startswith("A") for ref in comparison["prefixItems"][0]["properties"]["ref"]["enum"])
    assert all(ref.startswith("B") for ref in comparison["prefixItems"][1]["properties"]["ref"]["enum"])
    first = answer_schema(pack, span_ids=True, citation_first=True)["properties"]["first"]["properties"]
    assert list(first) == ["support", "reading", "limit"]
    draft["first"]["support"][0]["ref"] = "B1.W1"
    with pytest.raises(ValueError, match="wrong film"):
        resolve_span_answer(json.dumps(draft), pack)
    draft["first"]["support"][0]["ref"] = "A1.W999"
    with pytest.raises(ValueError, match="available"):
        resolve_span_answer(json.dumps(draft), pack)
