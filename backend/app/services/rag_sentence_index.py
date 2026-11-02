"""Derive local, revision-bound sentence offsets without changing source data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.rag_dense_trial import digest


def build_index(corpus: dict, segment, *, segmenter_version: str) -> dict:
    if digest({k: v for k, v in corpus.items() if k != "fingerprint"}) != corpus["fingerprint"]:
        raise ValueError("Corpus fingerprint failed.")
    result = []
    for document in corpus["documents"]:
        text = document["content"]
        previous = 0
        spans = []
        for start, end in segment(text):
            if type(start) is not int or type(end) is not int or not previous <= start < end <= len(text):
                raise ValueError("Sentence offsets must be ordered, nonoverlapping and in bounds.")
            if text[previous:start].strip():
                raise ValueError("Sentence segmenter omitted non-whitespace source text.")
            spans.append({"start": start, "end": end})
            previous = end
        if text[previous:].strip():
            raise ValueError("Sentence segmenter omitted the source tail.")
        result.append({"chunk_id": document["chunk_id"], "spans": spans})
    index = {"version": "source-sentence-index-v1", "corpus_fingerprint": corpus["fingerprint"],
             "segmenter_version": segmenter_version, "language": "en", "documents": result}
    index["fingerprint"] = digest(index)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3] / "data" / "evaluation"
    if any(not path.resolve().is_relative_to(root) for path in (args.corpus, args.output)):
        raise ValueError("Sentence experiment artifacts must stay project-local.")
    import spacy
    pipeline = spacy.blank("en")
    pipeline.add_pipe("sentencizer")
    def segment(text):
        return [(sent.start_char, sent.end_char) for sent in pipeline(text).sents]
    corpus = json.loads(args.corpus.read_text())
    index = build_index(corpus, segment, segmenter_version=f"spacy-{spacy.__version__}-blank-en-sentencizer")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2))
    print(json.dumps({"documents": len(index["documents"]),
                      "sentences": sum(len(d["spans"]) for d in index["documents"]),
                      "fingerprint": index["fingerprint"]}))


if __name__ == "__main__":
    main()
