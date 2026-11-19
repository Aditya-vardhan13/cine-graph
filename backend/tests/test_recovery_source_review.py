import hashlib
import importlib.util
from pathlib import Path
import pytest
from app.services.corpus_build_manifest import canonical_digest

spec=importlib.util.spec_from_file_location("source_review",
    Path(__file__).resolve().parents[2]/"scripts/bind_recovery_source_review.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_review_binds_exact_spans_and_refuses_wrong_film():
    docs=[]
    for qid in ("Q1","Q2"):
        content=qid+" makes a choice."
        docs.append({"chunk_id":qid,"film_qid":qid,"content":content,
            "content_sha256":hashlib.sha256(content.encode()).hexdigest(),
            "source_snapshot_id":"s-"+qid,"source_revision":"1"})
    corpus={"documents":docs,"cases":[{"case_id":"c","film_qids":["Q1","Q2"]}]}
    corpus["fingerprint"]=canonical_digest(corpus)
    notes=[{"case_id":"c","answerability":"complete","evidence":[
        {"passage_id":qid,"quote":qid+" makes"} for qid in ("Q1","Q2")]}]
    result=module.bind_review(corpus,notes)
    assert result["release_gold"] is False
    assert all(e["start"]==0 for e in result["cases"][0]["evidence"])
    notes[0]["evidence"][0]["quote"]="not in source"
    with pytest.raises(ValueError,match="quote"):
        module.bind_review(corpus,notes)
