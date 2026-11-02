import pytest

from app.services.rag_dense_trial import digest
from app.services.rag_sentence_index import build_index


def test_sentence_index_binds_source_and_does_not_discard_text():
    corpus = {"documents": [{"chunk_id": "C1", "content": "First. Second."}]}
    corpus["fingerprint"] = digest(corpus)
    index = build_index(corpus, lambda text: [(0, 6), (7, len(text))], segmenter_version="fixture")
    assert index["documents"][0]["spans"] == [{"start": 0, "end": 6}, {"start": 7, "end": 14}]
    assert index["fingerprint"] == digest({k: v for k, v in index.items() if k != "fingerprint"})
    with pytest.raises(ValueError, match="omitted"):
        build_index(corpus, lambda text: [(0, 6)], segmenter_version="fixture")
    with pytest.raises(ValueError, match="nonoverlapping"):
        build_index(corpus, lambda text: [(0, 6), (5, len(text))], segmenter_version="fixture")
