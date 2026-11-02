# CineGraph RAG experiment program v2

Status: research and evaluation design in progress; no model winner selected.

## Continuation: query planning and retrieval controls (2026-11-02)

Completed twenty-case offline replay against the same 465 frozen full passages.
No document re-embedding and no working-database reads or writes were needed:
the original Qwen4B native matrix was reused only after its content/order/run/
model cache key matched. The local Ollama digest was checked and the matrix
SHA256 recorded in the result. Every query branch stays within its selected film.

The first two question-only 4-bit Qwen3 instruction-planner prompts produced
valid JSON but narrowed the user's meaning: "injustice" became "systemic
injustice", with invented domestic settings or oppression. These plans were
rejected before retrieval. A versioned third experiment allows only exact
contiguous phrases from the question, enforced in code; the original question
is always retained. Seventeen of twenty plans passed that contract; three
fell back explicitly to the original question. Passing this contract does not
prove that a selected phrase retains all the original qualifiers or is useful.

The replay compares original-query dense retrieval, extractive-branch reciprocal
rank fusion, extractive round-robin diversification, the existing film-scoped
BM25 policy and original-query dense/BM25 equal-weight RRF. Branch depth is 30,
output depth 10, RRF constant 60. All variants use the same current span review;
there were no label changes in this comparison.

| Policy | Both-film source coverage @1 | @3 | @5 | @10 |
| --- | ---: | ---: | ---: | ---: |
| Qwen4B original query with film context | 1/14 | 8/14 | 9/14 | 13/14 |
| Extractive branches, RRF | 1/14 | 7/14 | 7/14 | 12/14 |
| Extractive branches, round-robin | 1/14 | 6/14 | 8/14 | 13/14 |
| Original query BM25 | 0/14 | 0/14 | 3/14 | 4/14 |
| Original dense + BM25 RRF | 1/14 | 3/14 | 5/14 | 8/14 |

Decision: none of these additions is promoted to live retrieval. They regress
near-top evidence visibility and add planning latency. Exact phrase extraction
often repeats most of the question rather than offering useful complementary
branches. More query variants are not inherently better. Native full-passage
dense retrieval remains the stronger development control, not a release winner.

These are coverage counts for fourteen supported, reviewed questions inside a
twenty-question development set, **not 93% answer accuracy**, not the original
20-case top-one criterion, and not an independent holdout. Six uncertain source
premises remain unresolved. The next distinct architecture experiment, trained
multi-vector late interaction, is reported below. Generation and fresh held-out writer
utility checks remain outstanding. Do not rerun another arbitrary weight sweep
on these twenty questions and call it generalisation.

Local artifacts (ignored): `data/evaluation/rag-v2/query-plans-v3-first20.json`
and `query-replay-v3-first20.json`. Reproducible policy/CLI entry point:
`app.services.rag_query_replay`; source visibility scoring remains
`rag_span_review`, not an automated answer-quality judge.

### Trained multi-vector architecture completed

Executed the official BGE-M3 trained projection at the same pinned encoder
revision used for the dense-window control. The adapter follows the
[official projection and normalization contract](https://github.com/FlagOpen/FlagEmbedding/blob/master/FlagEmbedding/finetune/embedder/encoder_only/m3/modeling.py)
and [inference token selection and mean MaxSim](https://github.com/FlagOpen/FlagEmbedding/blob/master/FlagEmbedding/inference/embedder/encoder_only/m3.py):
drop CLS, retain non-padding tokens including EOS, normalize each projected
token, then average each query token's maximum passage-token similarity.
No random projection, query expansion, learned sparse head or blended-score
tuning is involved. This is BGE-M3 late interaction, not a ColBERTv2 checkpoint.

All 931 source windows and twenty questions completed. Inputs and source-window
offsets match the existing dense-window representation. Token matrices use
float32 and approximately 646 MB of local disk (decimal units), materially
more than single-vector storage. Initial encoding took 99.1 seconds, excluding
model load and disk writes. A verified warm-cache replay scored a pair at p50
220 ms / p95 415 ms, excluding query encoding and model load; this is small-corpus
exact search, not a million-film production latency estimate. Accelerator batch
scoring agreed with the independent NumPy reference within 2.98e-8 on the
retained runtime parity check. Cached vectors also passed dimension, finiteness
and per-token normalization checks.

| Fixed-window architecture | Both-film source coverage @1 | @3 | @5 | @10 |
| --- | ---: | ---: | ---: | ---: |
| BGE-M3 dense CLS control | 0/14 | not re-tabulated | 4/14 | 6/14 |
| BGE-M3 trained token-level MaxSim | 0/14 | 4/14 | 6/14 | 7/14 |

Late interaction improves the BGE dense control's coverage here, but still
does not beat Qwen4B full passages (9/14 @5, 13/14 @10). It is not promoted.
The result argues against replacing the database or embedding architecture
on reputation alone. General semantic matching is still insufficient for some
multi-part narrative questions; evidence selection and supported interpretation
must be checked separately.

The next evaluation barrier is frozen separately in
`backend/tests/fixtures/rag-holdout-questions-v1.json`: twenty questions across
four pairs/eight films, disjoint from all ten pairs in the earlier development
set. Titles/years are grounded in the user-provided CSV. The questions have not
been ranked; source IDs and source-bound labels still need independent review.
This is a frozen question design, **not an already validated test set**. Do not
tune on its retrieval outputs or claim held-out accuracy before labels exist.

Runtime artifacts remain ignored locally: `bge-multivector-first20.json` records
the uncached run; `bge-multivector-verified-first20.json` records cache validation
and scoring parity. No live retrieval, database schema, source assertions or
user UI changed in this milestone.

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

## Initial executions and source-level diagnostic

The cleaned eight-film / first-20 corpus export contains 465 eligible passages.
Full-film exact dense retrieval is complete for Qwen 4B (native 2,560 dimensions)
and Qwen 0.6B (1,024 dimensions). Neither trial restricts source sections.
Uncached capture wall times were 739,747.6 ms and 98,075.7 ms respectively.
The batch sizes differ (2 vs 8), so this is not an isolated latency comparison
or a request SLO. Document vectors are retained in local resumable caches.

A separate 4B query ablation adds the target film title while reusing identical
document vectors. Its 40 query embeddings and capture took 13,860.7 ms warm.
This number excludes indexing and is not comparable to the uncached totals.

One source-aware development review has exact spans for P02-Q2 (first turn
toward a nonhuman relationship). Both opening plot passages support it. With
shared-question full-film retrieval, neither model returns both reviewed source
spans within top ten. Film-title query context brings the WALL-E opening into
4B's results at rank eight, while the first result is still cast commentary.
This is evidence of a query/ranking issue and one-case coverage recovery, not
an aggregate accuracy gain. No 20-question percentage is asserted from this
single-case review. The original top-one gate is unchanged.

E5's pinned files are now local. The common-window E5 run uses Metal, native
768-dimensional vectors, correct query/passage prefixes, and disabled network.
Results remain pending. A common-window Qwen comparison is required before
attributing any E5 gain to the encoder rather than the representation change.

## First controlled source-visibility results (2026-11-02)

All four common-window trials completed on the identical 931 source windows.
The initial source-aware review covers all 20 development questions: 14 have
defined supporting spans and six have unresolved direct-source coverage. This
is one agent's development review, not independent adjudication or a holdout.
Unresolved questions remain visible and require source/interpretive review;
they are not silently relabeled as retrieval failures or removed to claim 80%.

Counts below are questions where both films' **selected support spans** are
visible in the retrieved evidence. They are not graded relevance, answer
correctness, MRR, or the original pair-success@1 benchmark. Other valid
passages may be missing from the positive labels. Linked evidence groups
require all their component spans: a cast relation alone cannot prove a
relationship's narrative consequence.

| Configuration | Both-film span coverage @1 | @5 | @10 |
| --- | ---: | ---: | ---: |
| Qwen 0.6B full passage | 1/14 | 8/14 | 10/14 |
| Qwen 4B full passage | 4/14 | 9/14 | 10/14 |
| Qwen 4B full passage + target-film query | 1/14 | 8/14 | 12/14 |
| Qwen 0.6B common windows | 1/14 | 5/14 | 8/14 |
| Qwen 4B common windows | 3/14 | 6/14 | 8/14 |
| E5 base common windows | 0/14 | 0/14 | 5/14 |
| BGE-M3 dense common windows | 0/14 | 4/14 | 6/14 |

The union of these displayed top-ten pools covers the selected spans for 13/14
source-supported questions. This is only a candidate-visibility ceiling for
that union, not a production retrieval score. P03-Q2 remains absent under the
selected exact spans; inspect other valid evidence before declaring a source
or model failure. Near-duplicate overlapping windows also consume retrieval
slots, so window scores must be accompanied by unique-parent/context-budget
evaluation rather than treated as an automatic architecture improvement.

No winner is promoted. Prioritize pooled relevance review, candidate diversity,
and bounded reranking on a common pool; then test generated comparisons on
the same evidence. The measured first-rank weakness is still incompatible
with declaring the product's retrieval problem solved.

### Pooled-positive correction and fixed-pool reranker

Subsequent source review identified valid P03-Q2 alternatives already in the
captured pool: Eckhart's account of Dent's legal constraints, and Turan's
description of a deputy's misplaced confidence before being killed. Adding
those exact source spans changes the unchanged 4B film-context run's coverage
to 1/14 at one, 8/14 at three, 9/14 at five and 13/14 at ten. This is explicitly
a **label correction**, not a retrieval improvement. The preceding table is
the earlier selected-span diagnostic and must not be silently compared with
the revised labels. More alternative positives still need review.

A source-bound ten-candidate-per-film pool from that 4B film-context run is
now frozen for the quantized 4B reranker. It preserves all twenty questions,
including the unresolved ones, without using their labels in inference.
Checkpoints bind capture content, and the runner now accepts frozen prefixes
of up to fifty questions instead of requiring an artificial fifty-row input.
The experiment is pending. The first pair took 23,564.7 ms and 21,098.7 ms for
its two film sides; this flags a serious interactive-latency concern, not a
full latency distribution or proof that batching/other rerankers cannot help.
The next control should include a smaller cross-encoder on the same pool.

### Reasoning and instruction-following research follow-up

[BRIGHT](https://arxiv.org/html/2407.12883v3) distinguishes reasoning-heavy
retrieval from topical matching and experiments with query-side reasoning.
Our hypothesis, not a demonstrated film-domain result: questions about causal
choices, initial versus final states and analogous relationships may need a
bounded query plan rather than one broad question vector.

[FollowIR](https://arxiv.org/html/2403.15246v3) evaluates altered relevance
instructions and finds that many retrievers respond to instruction keywords
without honoring the conditions. This motivates counterfactual query controls
in CineGraph: first encounter versus ending, plot event versus attributed
critical interpretation, and protective choice versus subsequent consequence.
Success requires the requested evidence to change, not merely embedding the
extra words. No FollowIR score is claimed for our models.

[BRIGHT-Pro](https://arxiv.org/html/2605.04018v1), a 2026 preprint, expands narrow
positive sets into multi-aspect evidence and studies complementary retrieval
in static and iterative settings. This supports checking alternative positives
and complete evidence packs alongside single-passage metrics. Its results do
not establish a need for our own training or an unbounded agent loop.

The next pipeline ablation after fixed-pool reranking should compare the
unchanged question with a small, bounded plan of evidence needs, retaining the
original query branch. Such plans must be based on the question, not our gold
labels; invented movie events must never enter the evidence corpus. Any
generated query reformulation remains an ephemeral retrieval aid, not a fact.
First verify the observed rank/latency tradeoffs and alternative positives;
do not add a new production service or fine-tune a retriever on these twenty
inspected development questions.

The small reranker control is pinned to
`cross-encoder/ms-marco-MiniLM-L6-v2` revision
`233902d25c440f23af6f7d6e94d2946bac0bee0a`.
Its [official model card](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2)
documents pairwise sequence-classification logits. Our adapter scores exact
128-word source windows without truncation, then takes the maximum window
score per original candidate, preserving the winning span. This is a different
native input contract from full-passage 4B reranking, so any operational gain
must not be attributed solely to parameter count. Files are local; execution
is queued after the 4B run, not concurrent with it.

The question-planning candidate is
[Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
using its [4-bit MLX conversion](https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit)
at revision `50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b`. The official model
is non-thinking; the local conversion is approximately 2.26 GB. This is not an
embedding model or a source of movie facts. Its question-only planning contract
retains the original retrieval branch and permits at most three added queries.
The prompt cannot receive corpus text or gold labels. Syntactic validation
does not prove that generated queries preserve meaning or avoid invented
details; inspect those properties on the development questions and contrast
controls before using the plans in a retrieval quality claim.

## Completed fixed-pool reranker controls

All twenty frozen questions completed in both runs, using the same ten parent
passages per film and the revised pooled-positive review. Counts below still
refer to selected-span visibility on the fourteen source-supported questions,
not answer quality or the original twenty-question acceptance score.

| Selection | Both-film coverage @1 | @3 | @5 | @10 | Pair reranking p50 / p95 |
| --- | ---: | ---: | ---: | ---: | --- |
| No reranker (4B film-context retrieval order) | 1/14 | 8/14 | 9/14 | 13/14 | Not applicable |
| Quantized Qwen reranker 4B | 3/14 | 8/14 | 11/14 | 13/14 | 49.687 s / 52.474 s |
| MiniLM-L6 cross-encoder | 1/14 | 4/14 | 6/14 | 13/14 | 0.331 s / 0.681 s |

The MiniLM load took 393.9 ms separately. The Qwen run reported a peak MLX
allocator footprint of 2,795,617,576 bytes; this is not process RSS or a hard
OS memory cap. These are local experiment timings, not production SLOs.
Qwen consumes full passages; MiniLM uses maximum logit over exact source
windows due its input limit. Thus the operational comparison does not isolate
parameter count or batching alone. MiniLM's winning source span is retained.

Neither configuration is promoted. Qwen's modest coverage gain does not yet
justify its interactive cost, while MiniLM's fast execution loses useful
selected evidence near the top. The next test addresses query representation
and complementary evidence needs, keeping the unmodified retrieval branch.
Six unresolved questions and unreviewed alternative positives remain separate
quality work; they cannot be hidden by calling the fourteen-question subset
an 80-percent success on the original task.
