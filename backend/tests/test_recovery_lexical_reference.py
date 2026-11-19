import importlib.util
from pathlib import Path
import pytest
from app.services.corpus_build_manifest import canonical_digest

spec=importlib.util.spec_from_file_location("lexical_reference",
    Path(__file__).resolve().parents[2]/"scripts/evaluate_recovery_lexical.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_lexical_reference_binds_spans_without_claiming_answer_accuracy():
    documents=[{"chunk_id":qid,"film_qid":qid,"content":"A choice changes everything.",
                "content_sha256":"hash","section_title":"Plot"} for qid in ("Q1","Q2")]
    corpus={"documents":documents,"cases":[{"case_id":"c","film_qids":["Q1","Q2"],"question":"choice"}]}
    corpus["fingerprint"]=canonical_digest(corpus)
    review={"source_corpus_fingerprint":corpus["fingerprint"],"cases":[{
        "case_id":"c","answerability":"complete","evidence":[{
            "passage_id":qid,"film_qid":qid,"start":2,"end":8,"quote":"choice",
            "content_sha256":"hash"} for qid in ("Q1","Q2")]}]}
    result=module.evaluate(corpus,review)
    assert result["answer_accuracy"] is None
    assert result["summary"]["complete"]["included_annotated_spans"]["5"]==2
    review["cases"][0]["evidence"][0]["quote"]="wrong"
    with pytest.raises(ValueError,match="invalid_review_span"):
        module.evaluate(corpus,review)
