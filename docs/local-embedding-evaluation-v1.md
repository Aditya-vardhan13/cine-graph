# Local embedding evaluation v1

## Purpose

This is the decision gate between evidence preprocessing and a local vector
index. It evaluates a model without persisting vectors or changing any
canonical facts. A useful semantic neighbour is retrieval evidence, never a
proven relationship or an automatically displayed insight.

## Corpus boundary

The benchmark reads only eligible `EvidenceChunk` rows from the completed
`spacy-sentencizer-evidence-v3` run for
`english-1000-retained-narrative-v1`. Every row remains resolvable to its
`NarrativePassage`, source snapshot, attribution URL, and `CC BY-SA 4.0`
licence.

The current corpus has 24,194 eligible chunks from every one of the 1,000
collection films. The local report is deliberately written under `data/` (or
an explicit local output directory), which is ignored by Git.

## Retrieval ground truth

`ResearchAnswerEvidence` supplies the first benchmark set. For every retained
research answer with an explicit narrative-passage citation, the chunks derived
from that exact passage are relevant targets. This measures whether a natural
language research question retrieves its already-cited evidence; it does not
measure whether the answer is objectively true or whether the model invented a
theme.

The report records:

- Recall@10 — share of questions with an explicit target in the first ten;
- MRR@10 — rank-sensitive score for the first explicit target;
- the same metrics separated by evidence class;
- selected chunk count, tokenizer overflow count, matrix size, throughput, and
  per-question embedding latency.

This is a minimum regression benchmark. Before user-facing semantic discovery,
add a manually adjudicated held-out set covering comparisons, story devices,
production choices, reception, and cultural legacy. It must have source links,
negative examples, and no test question copied into a retrieval prompt.

## Candidate contract

The initial small ONNX candidates exposed a hard limit: BGE-small and MiniLM
truncate at 512 and 256 tokens respectively. They remain negative controls,
not selected index models. The measured Qwen candidates run through local
Ollama with truncation disabled:

| Candidate | Vector dimensions | Input limit | Query rule |
| --- | ---: | ---: | --- |
| `BAAI/bge-small-en-v1.5` | 384 | 512 | Use BGE's retrieval query instruction. |
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | 256 | Use the question unchanged. |
| `qwen3-embedding:0.6b` | 1,024 | 32,000 | CineGraph direct-evidence instruction. |
| `qwen3-embedding:4b` | 2,560 in the comparison | 32,000 | Same instruction. |

The limits are versioned in the evaluator rather than inferred from a private
runtime property. The report measures the source text with truncation disabled
and then restores the documented model limit. A candidate with meaningful
overflow is not silently accepted; its chunking/indexing policy needs a new
version.

## Running locally

The optional evaluator runtime is deliberately separate from the API runtime.
It avoids making live serving depend on a model package or its transitive
dependencies. Install its dependencies only in the local `cine-graph` Conda
environment; do not add weights, caches, vectors, or reports to Git.

```sh
PYTHONPATH=backend conda run -n cine-graph python -m app.services.embedding_evaluation \
  --collection english-1000-retained-narrative-v1 \
  --chunker-version spacy-sentencizer-evidence-v3 \
  --output-dir data/evaluation
```

Run each candidate independently while measuring it. The evaluator writes one
model/version/run-specific JSON report. Re-running the evaluator does not
alter the database.

Long builds are checkpointed after every batch as a NumPy memmap plus an
atomic progress file. An interrupted process resumes at the last completed
batch. The final cache identity binds the model, dimensions, chunk-run ID,
document representation, and every document content hash.

## Measured decision (2026-09-01)

The earlier 22–30% MRR result was an invalid product signal: it searched every
film for a question whose subject film was already known, and it mixed source
facts and critical interpretation into the narrative-embedding score. Correct
routing produced these narrative-only results on the current 11 source-linked
pilot questions:

| Method | Recall@10 | MRR@10 |
| --- | ---: | ---: |
| Qwen 0.6B, film scoped | 81.82% | 41.30% |
| Qwen 4B, film scoped | 100% | 60.32% |
| Qwen 0.6B, film + declared section route | 100% | 100% |
| Qwen 4B, film + declared section route | 100% | 100% |
| Qwen reranker 0.6B over Qwen 4B candidates | 100% | 60.91% |

The official Qwen3 Reranker 0.6B improved unfiltered 4B MRR by only 0.59
percentage points and took 5.44 seconds per query/candidate-method on this
machine. It is rejected from the live path. The section route is a declared
question-catalog policy (`story.*` to plot; `structure.*` to structure), not a
benchmark-tuned score adjustment.

Qwen 0.6B is selected for the v1 local index. The 4B model took 944 seconds to
embed only 532 benchmark-subject chunks (0.56 documents/second), while the
0.6B full 24,194-chunk build completed at 4.74 documents/second. Once the
validated cache was imported into pgvector, the warm end-to-end pilot retained
100% Recall@10 and 100% MRR@10. Query embedding latency was 132 ms p50 / 177 ms
p95 and PostgreSQL ranking was 5.5 ms p50 / 11.5 ms p95.

These results are promising enough for the local implementation, but not a
claim of production-quality generalisation. The gold set still has only 11
narrative questions across 10 films; the 200-question held-out gate remains
mandatory before a user-facing intelligence claim.

## Selection rule

Do not select a model on a leaderboard or size alone. Choose only after a
reproducible report shows all of the following:

1. it is licence-compatible with the intended use and the exact model source
   and version are recorded;
2. it has no unreviewed input truncation for eligible chunks;
3. it wins (or is not materially worse than) the other candidate on the
   source-linked benchmark, including across evidence classes;
4. its local throughput supports a bounded asynchronous build and its query
   time supports the product latency budget; and
5. a manual retrieval review finds no provenance or title/edition leakage.

The selected index is now implemented as the additive `EmbeddingModel`,
`EmbeddingIndexRun`, and `EvidenceEmbedding` schema. Model revision,
instruction hash, dimension, chunk-run ID, representation, configuration hash,
build progress, content hash, and source-linked chunk identity accompany every
materialisation. The application returns passages and source snapshot IDs as
candidate evidence; it never writes an `Assertion` or relationship.
