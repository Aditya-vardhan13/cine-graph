import importlib.util
from pathlib import Path

import pytest

from app.services.corpus_build_manifest import canonical_digest

spec=importlib.util.spec_from_file_location("recovery_fusion",
    Path(__file__).resolve().parents[2]/"scripts/fuse_recovery_rankings.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs():
    corpus={"documents":[{"chunk_id":str(i),"film_qid":"Q1","section_title":"Plot",
        "content":text} for i,text in enumerate(("An orchard.","A sacrifice saves his family."))],
        "cases":[{"case_id":"c","question":"sacrifice family","film_qids":["Q1"]}]}
    corpus["fingerprint"]=canonical_digest(corpus)
    dense={"contract":{"corpus":corpus["fingerprint"],"representation":"source-full-parent-v1"},
        "cases":[{"case_id":"c","question":"sacrifice family","sides":[{"film_qid":"Q1",
            "ranked":[{"chunk_id":d["chunk_id"],"text":d["content"],"start":0,
                "end":len(d["content"])} for d in corpus["documents"]]}]}]}
    return corpus,dense


def test_fusion_preserves_sources_and_explicit_rank_weights():
    corpus,dense=inputs()
    result=module.fuse(corpus,dense,dense_weight=1,lexical_weight=3)
    ranked=result["cases"][0]["sides"][0]["ranked"]
    assert ranked[0]["chunk_id"]=="1"
    assert ranked[0]["text"]==corpus["documents"][1]["content"]
    assert result["contract"]["retained_dense_sha256"]==canonical_digest(dense)


def test_fusion_cannot_silently_expand_a_window_to_full_parent():
    corpus,dense=inputs()
    dense["cases"][0]["sides"][0]["ranked"][0]["end"]-=1
    with pytest.raises(ValueError,match="ranking_source_span_mismatch"):
        module.fuse(corpus,dense)
