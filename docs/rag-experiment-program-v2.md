# CineGraph RAG experiment program v2

Status: research and evaluation design in progress; no model winner selected.

## Source-linked generation diagnostic (2026-11-02)

The first user question, Endgame versus The Godfather, was tested on a
balanced pack of the five highest-ranked complete passages per film with the
local Qwen3-4B-Instruct-2507 4-bit checkpoint. The evidence pack is drawn from
the frozen development corpus, without passing reviewed labels to the model.
It preserves full chunks and validates the actual tokenized prompt size.

An unconstrained attempt exceeded its output budget and produced malformed
JSON and mismatched quotes. An early schema-constrained implementation applied
the chat template twice. Those structured outputs are invalid **experiments**
and must not be used to compare model quality. The corrected implementation
feeds native chat-template token IDs to MLX once, and applies the official
Outlines schema logits processor directly.

The corrected greedy run selected immutable source-window IDs and resolved
those IDs back to exact source text. Its schema enforces one citation for each
film in the comparison. That citation-format contract passed, but a manual
source check failed: the model attributed the decision to end vendettas after
Sonny's death to Michael when the retained source says Vito. The output is
therefore not safe to ship. Exact substring binding and both-film citations
cannot prove entailment or reliably identify who performed an action. This is
one examined development case, not an estimate of model accuracy.

Research on [attribute-first generation](https://aclanthology.org/2024.acl-long.182/)
and [ALCE citation evaluation](https://aclanthology.org/2023.emnlp-main.398/)
supports separating evidence selection, answer quality and attribution review.
The span-ID diagnostic is inspired by this distinction; it is not a
reimplementation or a reproduction of either paper's method or results.

The official model card recommends non-greedy sampling; a seeded
temperature-0.7, top-p-0.8, top-k-20 experiment is implemented separately.
Its presence penalty uses a documented 2,048-token local window, rather than
claiming exact parity with every serving implementation. On this same case,
the sampled result also attributed Vito's decision to Michael, and the schema's
character bound cut the scene idea off mid-sentence. Citation validity alone
initially missed the latter; the deterministic validator now rejects visibly
unfinished readings and scene ideas. A single seed and single question cannot
establish whether sampling generally helps. A newer pinned
Qwen3.5-4B checkpoint was being downloaded for a controlled comparison, but
the transfer was paused when free disk approached 6 GiB. Two partial files are
retained locally; no completed comparison is claimed. Docker was unavailable,
so the separate holdout-film database and source review were not run.

These trials are offline only: no live retrieval, prompt or production API has
changed. A separately reviewed, film-pair-disjoint evaluation remains necessary
before claiming usefulness or an 80% quality target. Tests of schema validity
are deliberately not answer-quality scores.

### Citation-first four-pair development check

One question per development pair was selected in advance (P01-Q1 through
P04-Q1), using the same Qwen4B retrieval rankings and source packs. Constrained
decoding required both films in the comparison and generated source IDs before
each interpretation. Four outputs passed the then-current syntax/reference
contract; revalidation using the subsequently strengthened completeness rule
rejects P02-Q1 for a cut-off limitation. All four need more than structural
validation and are not approved for a writer-facing feature:

- **Endgame / Godfather:** improved attribution of Vito's decision versus the
  earlier draft, but incorrectly attributes a filmmaker's comment and its
  selected quote fragments do not cover every claim in the reading.
- **Her / WALL-E:** the response makes broad claims about both artificial
  relationships without adequately distinguishing the human's relationship in
  *Her* from the robots' relationship in *WALL-E*. Its limitation is truncated.
- **Dark Knight / No Country:** some source-grounded villain analysis is
  relevant, but it does not clearly establish the asked-for moral rule of a
  protagonist in each film and selected fragments under-support specific claims.
- **Jaws / Jurassic Park:** the second reading asserts a warning was ignored,
  while its cited fragment establishes disabled fences and the ensuing attack,
  not that Nedry ignored a warning. The comparison therefore forces the premise.

This is one developer's source-aware review, not an independent rating or a
representative success-rate estimate. The observed quotation windows can begin
or end mid-sentence. A separate, source-fingerprinted English spaCy sentencizer
index and opt-in sentence-ID experiment were prepared to test whether complete
sentence citations help. The stored evidence is never rewritten. Sentence
boundaries can still be wrong, and a correct quotation can still fail to support
the claim. Other languages require their own explicitly selected segmenter.

The sentence-index run produced 3,377 spans over 465 frozen passages. It
preserves source offsets and rejects gaps containing non-whitespace text. Ten
spans under twelve characters are ineligible as citations and explicitly
reported; none in this corpus exceeded the 2,500-character source-span limit.
This is model-free English segmentation, not ground-truth semantic analysis.

Two of four sentence-ID cases completed before local disk headroom fell below
the experiment's 6 GiB reserve during inference; the process was stopped and
its two per-case checkpoints retained. Free space recovered after the process
ended, consistent with memory pressure and swap, but the precise cause was not
measured. In P01-Q1, the citation for the Romanoff sacrifice was an unrelated
cast-list sentence. In P02-Q1, the citation for a claim about human isolation
was a sentence about EVE being sent to diagnostics. Both outputs met the
reference-format contract but failed direct citation-support inspection.
Complete sentence boundaries improve readability, not semantic relevance.
No result is claimed for the remaining two cases.

The offline runner now checks free space before each case and periodically
during streamed token generation. If the reserve is crossed, it stops without
overwriting completed case checkpoints. This cannot guarantee protection during
initial model loading or prompt prefill; adequate free disk and memory still
need to be available before running. Streaming output preservation and the
low-space stop policy are covered by pure tests; see the live run below.

On 2026-11-03 the guarded streaming runner completed a real P03-Q1 local
inference, with a normal stop after 460 output tokens (approximately 15.3
generation tokens/s and 163.8 prompt tokens/s for that single run). Its source
IDs and JSON structure validated; this is not an entailment or usefulness
assessment. Memory and latency are local measurements, not production SLOs.

The eight frozen holdout titles were matched to explicit candidate Wikidata
identities and found in `cinegraph_eval`. The selected, completed recovered
Wikipedia v1 chunk run contains 184 eligible chunks for these films and was
exported read-only to a fingerprinted local corpus, without ranking. The two
retained passage records per film use separate legacy/recovered records for
the same Wikipedia revision: they are not independent sources. This export
uses the recovered v1 extraction and v3 chunker, whereas the four-pair
development canary uses parser v2 and chunker v4. Extraction differences must
be accounted for before comparing their results. Identity/source review and
source-bound relevance labels are still missing; this is not gold or a scored
holdout. The corpus fingerprint is
`b6638287c54c9f05f1a23da7e1585a687c976ea97fa7fc5cb03bfad09f06562b`.

#### Holdout source audit and language-template loss

On the eight unranked holdout films, a simple markup diagnostic flagged 26 of
184 eligible recovered-v1 chunks; the separate parser-v2 canary flagged 0 of
182. This detector is only a presentation warning, not a completeness or
accuracy score. Directly inspecting the retained Black Swan snapshot exposed
an important counterexample: both older extractions dropped the visible text
inside `{{lang|it|...}}`, leaving a dancer's role blank. Thus removal of markup
alone had concealed missing information.

An **eval-only**, additive parser-v3 canary preserves the visible second
parameter of `lang` templates while retaining the previous media and reference
handling. It does not change the default v2 parser, raw snapshots, live corpus,
or assertions. Using the same eight verified snapshots and chunker v4, the v3
run created 210 chunks, 28 excluded by quality rules, with 182 eligible. A
rerun reused all 210 and preserved the 28 excluded count. Comparing the 182
v2 and v3 eligible chunks by source/section/ordinal produced two changed chunks
and no unmatched keys: the restored dancer role in the plot and descriptive
words in a critical-review sentence. This verifies those two examples, not
complete preservation of all possible Wikipedia template types.

The preliminary, single-reviewer holdout draft now covers all 20 questions:
11 marked supported and 9 uncertain under its narrowly defined facets, with
45 exact source quotations. All 45 quotes occur uniquely in the corresponding
film's v3 chunks. This is a quote-preservation diagnostic only: labels were
authored against v1, were not silently migrated to v3, and still need source
and independent review. No holdout ranking has been run. The v3 export's local
fingerprint is `dc5e56b02be3f6767539696bfe876080133ebea26976dd684be431198637d663`.
The read-only `rag_source_rebinding_audit` verifies the source and target
fingerprints, identical frozen questions and film identities, exact source
snapshot ID, and every quote's exact offsets. Its separate output contains
candidate locations, not a review artifact accepted by the relevance scorer.
On this local comparison it reports 45 unique, zero missing and zero ambiguous
locations. A location match alone is not independent source review.

The source canary rerun also exposed a preprocessing accounting defect:
previously excluded chunks were counted only on creation, so a rerun could
overwrite its excluded total with zero. Reused excluded chunks now remain in the
total; the regression uses a separate collection in `cinegraph_test` and the
evaluation canary rerun confirmed 28 excluded chunks remain reported.

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

## Revised dataset-first execution plan (3 November 2026)

The dated source review is in
[the external-data audit](open-narrative-datasets-audit-2026-11.md). Persistent
continuity is in [project memory](project-memory.md) and the
[narrative research skill](skills/cinegraph-narrative-research/SKILL.md).

### Completed: separate usable source evidence from benchmark answers

Pinned SemEval narrative similarity and MF² releases now have an offline,
versioned preparation adapter. The current validated local run is
`data/evaluation/external-prepared/v1-run4/`:

- 1,325 evidence documents: **1,219 distinct story summaries** (not all films),
  53 MF² transcripts and 53 synopses. These are not 1,325 new catalog films.
- 5,051 exact 160-word/32-word-overlap passages linked to parent offsets.
- 2,369 benchmark inputs and separately stored gold rows: 639 SemEval triples
  and two independent claims for each of 865 eligible MF² pairs.
- Three identical fact/fib pairs quarantined, never silently repaired.
- Retained raw captures and hashes; every derivative source-bound. Subtitle
  rendering removes counters/times but maps dialogue back to raw character
  offsets. Negative cue indices and fractional timestamps are not story facts;
  two orphan blocks remain untimed. No speaker names are inferred.
- 59,475 subtitle source spans verified, no parsing errors in the selected run.
  This proves preservation, **not transcription accuracy**; visible noise in
  transcript 32 warrants separate source-quality review.
- Gold labels/comments/annotation dimensions are absent from model inputs and
  evidence. MF² true/false arm order is deterministically counterbalanced.
- Nominal identity metadata stays unreviewed. Test identity metadata is
  explicitly projected from the original release's label-bearing file, with
  its source locator; answer labels themselves remain in the gold artifact.

An existing two-document BM25 policy is the cheap development-only control:
111/200 correct (55.5%), zero ties. This is relative whole-story similarity,
**not** user-question evidence retrieval, generated-answer correctness or
writer usefulness. No test ranking or test model generation has been run.

### Gate 1: source detail, rights and identities before product ingestion

Use these sources locally for research now; keep them outside live product
evidence until canonical film identity and per-asset usage are reviewed. MF²
release-level CC BY 4.0 is not automatic proof of every subtitle's upstream
rights. SemEval attribution/share-alike and original canaries must survive use.
Do not mix novels into the English film catalog. Future approved ingestion must
use existing snapshot/passage/assertion boundaries, not a parallel fact graph.

Review a stratified sample of each source kind for broken extraction, speaker
ambiguity, transcript quality and whether requested facts are even observable.
MF²'s visual-only questions require sufficient visual evidence or an explicit
text-only support label; full-benchmark text scores cannot establish film-level
understanding. No new bulk scraping is needed for this gate.

### Gate 2: external benchmarks without split contamination

Preserve official splits. SemEval has 164 exact story strings shared by dev/test.
Only 92 test triples are text-disjoint from dev+sample, and only **61** also have
nonoverlapping supplied Wikidata work IDs after conservative identity checking.
This is a candidate external evaluation subset, not proof that pretrained
models have never seen the stories. Freeze and retain its IDs before evaluating.
Never tune on it or call both task tracks independent training examples.

Compare whole-story embedding similarity on SemEval development data first;
report triplet accuracy, ties and breakdowns, keeping supplied interpretations
in gold only. Keep our own pairwise user-question evidence tests: external
similarity and claim verification are complementary controls, not replacements.

### Gate 3: fixed-evidence quantized generation comparisons

Once source sufficiency is established, compare the locally available Qwen 3
4B and 8B Q4_K_M checkpoints on identical bounded evidence, prompts, sampling
and output budgets. Distinguish these from Qwen3-4B-Instruct-2507 MLX weights;
changing checkpoint family/runtime is not an isolated size comparison.

Start with source-bound claim diagnostics and our existing comparison questions.
Record evidence support, correct character attribution, answered facets,
limitations/abstention, latency and memory/disk footprint. Only an independent
writer review can establish creative usefulness. FP16/distillation is not a
default fix: quality retention needs a separate control and memory feasibility.
Do not load models while the retained disk-headroom guard would fail.

### Execution and regression rules

Commands:

```sh
conda activate cine-graph
python scripts/prepare_narrative_benchmarks.py --output data/evaluation/external-prepared/<new-run>
python scripts/validate_narrative_preparation.py data/evaluation/external-prepared/<new-run>
PYTHONPATH=backend python -m pytest backend/tests/test_external_narrative_preparation.py backend/tests/test_narrative_benchmark_acquisition.py -q
```

Use one background job handle and durable run report; do not duplicate quiet
work. Earlier failed/intermediate runs remain for diagnosis; do not point new
experiments at them. No product UI, operational DB, model weights or retrieval
defaults changed in the preparation milestone. Product promotion still needs
its PostgreSQL/API/browser gates, not just these offline preparation checks.

### MF² label-blind retrieval diagnostic

The offline worker `scripts/build_narrative_retrieval_packet.py` completed a
film-scoped diagnostic-development subset: 190 claim queries across five films,
with 1,540 claim queries outside this subset. The worker did not open gold labels
or load a model. Its lexical top-six passages are unscored research leads, not
validated answers. This subset derives from the release's official test data and
is no longer an untouched test set. The frozen contract and results remain local
under `data/evaluation/external-prepared/`.

### Whole-story embedding development control

The project-local Qwen3 embedding 0.6B Q8_0 model (digest
`ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`)
encoded 479 distinct development stories in about 57 seconds on the local M1.
Symmetric whole-story cosine produced 121/200 correct (60.5%), zero ties;
the earlier two-candidate BM25 control scored 111/200 (55.5%). On paired cases,
both were correct 69 times, both wrong 37, embedding alone correct 52 and
BM25 alone correct 42. This is a small, inspected development set; the ten-case
difference does not establish general superiority. The underlying model may
already have encountered these stories during pretraining.

The source-preserving evaluation artifacts and vectors are local in
`data/evaluation/external-prepared/semeval-qwen06-dev-run1/`. No held-out cases
were evaluated, no retrieval settings changed, and no model or dataset was
promoted into the product. This compares whole-story similarity, not the
question-conditioned film-pair or writer-usefulness objective. The worker
checked the six-GiB disk reserve between batches and refused truncation.

The same 200 development comparisons were subsequently run with the locally
cached BGE-M3 dense CLS representation, float32, CPU, pinned revision
`5617a9f61b028005a4858fdac845db406aefb181`: **118/200** matches, no ties,
approximately 105 seconds of embedding/scoring. Compared with Qwen 0.6B,
both matched on 89 cases, both missed 50, Qwen alone matched on 32, and BGE
alone matched on 29. This is not evidence that either generalizes better; it
is the same small development set and does not test BGE's sparse or multi-vector
retrieval. The two runtimes, devices and batching differ, so timings are not an
isolated hardware or model-size comparison.

The initial MPS attempt failed because the Conda PyTorch has no MPS support;
the Conda CPU attempt rejected the PyTorch checkpoint because its installed
torch version is below the security threshold. No security check was bypassed.
The successful CPU run used the already-existing project-local `rag-encoders`
environment with torch 2.8. The output and vectors remain local under
`data/evaluation/external-prepared/semeval-bgem3-dev-run3/`; no held-out cases
were evaluated and no product configuration was changed.

### Frozen source-identity-disjoint external subset

After the development controls, 61 test case IDs were frozen before either
model was run, using `scripts/freeze_narrative_holdout.py`; the manifest records
the exact prepared-corpus hashes and did not open gold labels. The two selected
models used the same 170 distinct story summaries, whole-story symmetric cosine,
and fixed cases. Predictions were written before scoring. Results:

| Method | Label matches / 61 | Ties |
| --- | ---: | ---: |
| Qwen3 embedding 0.6B Q8_0 | 37 | 0 |
| BGE-M3 dense CLS float32 | 40 | 0 |
| Two-candidate lexical control | 38 | 0 |

For the two embedding models, both matched 33, both missed 17, Qwen alone
matched four and BGE alone matched seven. The sample is too small and stories
can occur in multiple triples, so these are not independent Bernoulli trials or
evidence of a statistically reliable model winner. The lexical score is an
additional post-run baseline, not a newly tuned method. Identity disjointness
uses supplied, unreviewed IDs; model pretraining exposure is unknown.

This is an external story-similarity check, **not** evidence that our product
answers a writer's question, understands a scene, or retrieves good passages.
No source, labels or vectors were added to the live corpus or committed. Local
artifacts retain the frozen-manifest fingerprint. The worker's first report
version string included `dev` even on these runs; its explicit `split` and
manifest fingerprint identify the actual test scope. The next schema version
removes that misleading suffix.

The original worker parsed all 400 test-label JSON rows into memory after
predictions before filtering down to the frozen 61; only those 61 were scored
or printed. This does not affect those predictions, but was broader access than
intended. The worker now filters IDs before parsing label JSON. Treat the
remaining test labels as not manually inspected, not as technically unread.

### Read-only catalog overlap: why research data is not yet product data

An explicit read-only `cinegraph` database audit compared 1,219 distinct
SemEval story summaries against existing `films.wikidata_id`, without writing
database records. Eight summaries had a single exact-QID film candidate; 219
had conflicting/multiple or invalid IDs; 992 had no exact match in the current
film table. The data includes novels and other works, so the last count is not
the number of missing movies. Some synopsis text may already exist from the
same underlying Wikipedia article, so an exact identity match does not prove
it adds useful new evidence.

Candidate IDs and provenance remain local in
`data/evaluation/external-prepared/semeval-catalog-candidates-v1.json`, all
marked `review_required` and not operationally eligible. The audit does not
resolve identity, assess source rights, deduplicate against existing passages,
or insert evidence. Before any product import, independently verify identity,
original article attribution/licence and duplicate-content impact; keep
benchmark-held-out records isolated from model/evaluation tuning.

The audit can be repeated with `scripts/audit_external_catalog_overlap.py`;
it requires an explicit local `CINEGRAPH_AUDIT_DSN` and starts a database
read-only transaction. Its results are a snapshot of the catalog at run time.
Future corpus expansion needs more suitable cleared sources, not a claim that
this benchmark alone supplies 1,219 additional film records.

### Existing passage check for the eight identity candidates

`scripts/audit_external_passage_overlap.py` subsequently compared the eight
exact-QID candidates with the current `narrative_passages` projection in a
read-only catalog transaction. Six had no records in that projection; this
does **not** prove that they have no older `narrative_documents` or other
catalog information. Two had existing plot passages:

- `3 Deewarein`: 11 existing narrative passages;
  one plot-snapshot comparison shared 92.9% of unique five-word candidate
  shingles with the existing plot text.
- `The Music Room` / `Jalsaghar`: 16 existing narrative passages; one plot
  comparison shared 0% of unique five-word candidate shingles. This is a
  candidate for source review, not proof that the synopsis is novel or correct.

The script groups plot passages by retained snapshot and reports source URL,
revision and licence; detailed indicators remain local under
`data/evaluation/external-prepared/semeval-passage-overlap-v1.json`. Five-word
overlap is a lexical screening heuristic: it cannot establish semantic
equivalence, authorship, licence compliance or suitability for users. The
benchmark snapshot does not itself establish a specific Wikipedia revision for
each summary; source attribution and identity review remain prerequisites to
any product-facing use. No database records were inserted or updated.

The follow-up read-only check also examined legacy `narrative_documents` joined
through `corpus_records`, rather than assuming the newer passage projection was
the whole catalog. One of the six films without newer passages, `Bullseye!`,
has a matched legacy plot summary; 76.1% of the candidate's unique five-word
shingles appear in that document. Five candidates had neither a newer narrative
passage nor a legacy narrative document linked to the matched film at audit time.
These remain unreviewed candidates—not five approved additions. For example,
the matched `Roma` is the 1972 Federico Fellini film, not the 2018 film; its
Wikidata identity is [Q18423](https://www.wikidata.org/wiki/Q18423). Language
edition, title identity, source licence and attribution must be resolved before
adding anything to the user-facing collection.

The revised report, including legacy document IDs, match status, access scope
and source links, is local at
`data/evaluation/external-prepared/semeval-passage-overlap-v2.json`. As above,
lexical overlap is an indicator, not a legal or semantic duplicate decision.
