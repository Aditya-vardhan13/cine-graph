import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from app.services.corpus_build_manifest import canonical_digest

spec=importlib.util.spec_from_file_location("convert_reranking",Path(__file__).resolve().parents[2]/"scripts/convert_recovery_reranking.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_converter_binds_candidate_sources_and_rejects_incomplete():
    docs=[{"chunk_id":q,"film_qid":q,"content":"source","source_snapshot_id":"s"} for q in ("A","B")]
    case={"case_id":"c","question":"why?","film_qids":["A","B"]}
    corpus={"documents":docs,"cases":[case]}; corpus["fingerprint"]=canonical_digest(corpus)
    capture={"corpus_fingerprint":corpus["fingerprint"],"cases":[{**case,
        "first_pool":[docs[0]],"second_pool":[docs[1]]}]}
    fingerprint=hashlib.sha256(json.dumps(capture,sort_keys=True).encode()).hexdigest()
    result={"capture_fingerprint":fingerprint,"complete":True,"model":"4b","instruction":"test",
        "cases":[{**case,"first_ranking":[{"chunk_id":"A","score":0.2}],
                    "second_ranking":[{"chunk_id":"B","score":0.1}]}]}
    assert module.convert(corpus,capture,result)["cases"][0]["sides"][0]["ranked"][0]["text"]=="source"
    result["complete"]=False
    with pytest.raises(ValueError,match="incomplete"):
        module.convert(corpus,capture,result)
    result["complete"]=True
    result["cases"][0]["first_ranking"][0]["chunk_id"]="B"
    with pytest.raises(ValueError,match="candidate_set"):
        module.convert(corpus,capture,result)
