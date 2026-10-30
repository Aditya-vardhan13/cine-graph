# CineGraph RAG experiment program v2

Status: research and evaluation design in progress; no model winner selected.

## Objective and assumptions

The product must help a writer answer a specific question about two films,
inspect the supporting passages, and develop an original alternative. More
parameters, more retrieved text, and a larger database are hypotheses, not
acceptance criteria. Retrieval, interpretation and creative usefulness need
separate measurements. Local experiments never write the working corpus.

The measured first-20 development baseline remains 9/20 directly supported
pairs at rank one. Its four-head oracle is 12/20. These questions have been
inspected repeatedly and are not a holdout. A perfect selector over those
four heads cannot reach 16/20; deeper evidence and the question premises must
be examined before another reranker sweep.

## Research grounding

- [Dramatron](https://arxiv.org/abs/2209.14958), with an accompanying
  [author project account](https://google-deepmind.github.io/dramatron/details.html),
  studies hierarchical co-writing with 15 industry professionals. Its relevance
  is editable idea exploration and writer control; it does not validate film
  evidence retrieval or an autonomous finished screenplay.
- [ScreenWriter](https://arxiv.org/html/2410.19809v1) reconstructs screenplay-like
  descriptions from video, then uses scene-aware hierarchical summarisation.
  This is not a writing-assistant RAG benchmark. Our inference: retain event
  order, character identity and surrounding context rather than reducing all
  narrative evidence to interchangeable paragraphs. No video ingestion is
  required for the present experiment.
- [StoryWriter](https://arxiv.org/html/2506.16445v1) separates event outlining,
  planning and writing, and reports human and automated ratings. Its evaluation
  includes relevance, coherence, empathy, surprise, creativity and complexity.
  Its generation results do not establish retrieval quality or prove that a
  local 4B model will meet our needs.
- [Qwen3 Embedding](https://arxiv.org/abs/2506.05176) motivates comparing small
  and larger instruction-aware dense models under a fixed protocol. General
  benchmark rankings are not evidence of CineGraph domain accuracy.
- [BGE-M3](https://arxiv.org/html/2402.03216v3) supports dense, learned sparse
  and multi-vector representations. Those modes must be identified explicitly:
  a dense-only Ollama result is not an evaluation of BGE-M3's full architecture.
- [ColBERTv2](https://arxiv.org/html/2112.01488v3) provides token-level late
  interaction with compression. It motivates a distinct architecture control,
  not an immediate production index replacement.

## Controlled experiment matrix

Four embedding candidates: Qwen3-Embedding-0.6B (current control),
Qwen3-Embedding-4B (existing local quantized model), BAAI/bge-m3, and
intfloat/multilingual-e5-base. Pin exact model revision, tokenizer, pooling,
normalisation, dimension, quantization and query/document prefixes in each run.
Check the official model cards before executing new adapters. Weights and
caches go under ignored project-local data paths; never global caches.

First compare models on identical cleaned passages, identical film scopes,
and exact cosine search. Keep native dimensions offline; do not alter the live
1024-dimensional schema for experiments or silently compare shortened vectors
against full-dimensional alternatives. Include a lexical control. A previously
reviewed 96-candidate subset is not a full-corpus embedding comparison.

Then hold the strongest two model configurations fixed and compare:

1. Dense passage retrieval.
2. Lexical+dense fusion with documented fixed weights.
3. Short-window retrieval returning the same-revision parent context, with
   bounded context length and no generated text substituted for source prose.
4. Token-level late interaction on the small corpus if supported locally;
   record storage/latency and label unsupported runs as not executed.

Hard section filters, soft section priors and whole-film search are separate
ablations. Do not change chunking, model, query rewriting and reranking together.
Run one model job at a time with resumable content-addressed caches.

## Evaluation repair before selection

For each question record requested facets, whether its premise is supported,
and exact supporting spans for each film. Distinguish missing source evidence,
candidate miss, ranking miss, incomplete evidence pack and unsupported synthesis.
Allow a pair to differ; a useful answer may reject a claimed similarity.

Keep the original pair-success@1 and its 80% target unchanged. Add per-film
span recall@5/10, nDCG with graded labels, both-film facet coverage under a fixed
context budget, and abstention precision/recall. Unknown labels are not negatives.
Use rank-blind pooled candidates from every contender, with content hashes and
reviewer provenance. Model-assisted labels are provisional, not independent gold.

Use the current 20 questions for diagnosis, the inspected 50 for development
regression, and a new film-pair-disjoint holdout for a release-quality claim.
Freeze the holdout before ranking it; do not inspect it during tuning. Report
counts and confidence intervals, not only a headline percentage.

Only after retrieval selection compare no reranker, the existing 0.6B and
quantized 4B rerankers on the same candidate union. Then compare local 4B/8B
generation on the same evidence packs: claim support, citation completeness,
question coverage, useful contrasts, premise correction and writer-editability.
Creative output needs a separate writer review; citation syntax is not factual
support, and retrieval accuracy is not willingness to pay.

Record cold/warm p50/p95 by stage, peak memory, disk usage, input/output sizes
and failures. Choose the simplest configuration with a defensible quality gain
and acceptable local latency. No production promotion until integration/browser
regression tests and a heldout quality review pass.

## Verified starting point (2026-10-31)

The local first-20 v2 rerun returned identical top-three IDs to its retained
capture. Query embedding batch: 1,995.88 ms; combined database ranking for
80 film/policy retrieval calls: 1,232.79 ms. These are one-run diagnostic timings,
not endpoint p95. The 242-item top-three review packet is not yet fully labeled.
The isolated integration suite passed 65 tests and Playwright passed 7 flows.
These validate functionality, not answer quality. The experiment goal remains open.

## Encoder runtime checkpoint

The existing Conda interpreter reports x86_64. Encoder experiments have a
separate project-local arm64 Python 3.11 environment at
`data/venvs/rag-encoders`, installed from
`backend/requirements-rag-experiments.txt`. This does not change Conda or the
API environment. Native PyTorch 2.8.0 and NumPy 2.2.6 import successfully;
Metal is available outside the restricted sandbox (the sandbox reports it
unavailable). Record the actual device per run; do not compare sandbox CPU
timings to unrestricted Metal timings as if they were model-size effects.

Official repository revisions resolved for the next encoder trials:

- E5 base: `d128750597153bb5987e10b1c3493a34e5a4502a`.
- BGE-M3: `5617a9f61b028005a4858fdac845db406aefb181`.

The official BGE repository has `pytorch_model.bin`, not safetensors; its
adapter uses PyTorch's restricted weights-only loader, with remote code
disabled. These are runtime preparations, not completed model evaluations.
