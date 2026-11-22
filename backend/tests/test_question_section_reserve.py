import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location("section_reserve",
    Path(__file__).resolve().parents[2]/"scripts/evaluate_question_section_reserve.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_routes_only_from_question_text_and_gives_reception_priority():
    assert module.requested_section("What choices put the characters at risk?") == "plot"
    assert module.requested_section("How did critics discuss the director's choices?") == "reception"
    assert module.requested_section("How did the camera create tension?") == "production"
    assert module.requested_section("What does this mean?") is None


def test_reserve_two_sections_without_losing_candidates_or_crossing_film_scope():
    ranked=[{"chunk_id":str(i),"film_qid":"Q1"} for i in range(7)]
    parents={str(i):{"film_qid":"Q1","section_title": "Plot" if i in (4,6) else "Cast"}
             for i in range(7)}
    selected=module.reserve(ranked,parents,"Q1","plot")
    assert [r["chunk_id"] for r in selected[:5]] == ["0","1","2","6","4"]
    assert {r["chunk_id"] for r in selected} == {r["chunk_id"] for r in ranked}
    assert module.reserve(ranked,parents,"Q1",None) == ranked
    parents["6"]["film_qid"]="Q2"
    with pytest.raises(ValueError,match="candidate_outside_film"):
        module.reserve(ranked,parents,"Q1","plot")
