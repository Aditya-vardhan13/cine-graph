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


def retained_inputs():
    documents=[{"chunk_id":qid,"film_qid":qid,"content":"A choice changes everything.",
                "content_sha256":"hash","section_title":"Plot"} for qid in ("Q1","Q2")]
    corpus={"documents":documents,"cases":[{"case_id":"c","film_qids":["Q1","Q2"],"question":"choice"}]}
    corpus["fingerprint"]=canonical_digest(corpus)
    review={"source_corpus_fingerprint":corpus["fingerprint"],"cases":[{
        "case_id":"c","answerability":"complete","evidence":[{
            "passage_id":qid,"film_qid":qid,"start":2,"end":8,"quote":"choice",
            "content_sha256":"hash"} for qid in ("Q1","Q2")]}]}
    ranking={"contract":{"corpus":corpus["fingerprint"],"representation":"test-window"},
        "cases":[{"case_id":"c","question":"choice","sides":[{
            "film_qid":qid,"ranked":[{"chunk_id":qid,"film_qid":qid,"score":0.5,
                "start":0,"end":8,"text":"A choice"}]} for qid in ("Q1","Q2")]}]}
    return corpus,review,ranking


def test_retained_window_must_cover_whole_reviewed_span():
    corpus,review,ranking=retained_inputs()
    assert module.evaluate(corpus,review,retained_ranking=ranking)["summary"]["complete"]["included_annotated_spans"]=={"5":2}
    item=ranking["cases"][0]["sides"][0]["ranked"][0]
    item.update(end=7,text="A choic")
    result=module.evaluate(corpus,review,retained_ranking=ranking)
    assert result["summary"]["complete"]["included_annotated_spans"]=={"5":1}


@pytest.mark.parametrize("change,error",[
    ("corpus","ranking_corpus_mismatch"),
    ("question","ranking_question_or_film_mismatch"),
    ("film","ranking_question_or_film_mismatch"),
    ("text","ranking_source_span_mismatch"),
    ("score","ranking_invalid_candidate"),
])
def test_retained_ranking_rejects_mismatched_inputs(change,error):
    corpus,review,ranking=retained_inputs()
    row=ranking["cases"][0]
    if change=="corpus": ranking["contract"]["corpus"]="other"
    elif change=="question": row["question"]="other"
    elif change=="film": row["sides"][0]["film_qid"]="Q3"
    elif change=="text": row["sides"][0]["ranked"][0]["text"]="altered"
    elif change=="score": row["sides"][0]["ranked"][0]["score"]=float("nan")
    with pytest.raises(ValueError,match=error):
        module.evaluate(corpus,review,retained_ranking=ranking)
