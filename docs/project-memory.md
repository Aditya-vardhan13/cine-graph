# CineGraph project continuity

Updated 3 November 2026 at the user's explicit request. This is project-local
memory; it does not change user-global Codex configuration or other projects.

## Objective

Help writers study films, investigate their own questions, compare concrete
choices/conflicts/consequences, and develop original writing moves. Retrieval
and generated analysis must answer the question, not dump related passages.
Build for the present with additive source/model/language boundaries; avoid
new services or generic architecture solely to sound scalable.

## Research-data checkpoint

See `docs/open-narrative-datasets-audit-2026-11.md` for dated research and source
links, and `docs/rag-experiment-program-v2.md` for the active experiment plan.
SemEval-2026 Task 4 and MF² text releases are pinned under
`data/evaluation/external/`. All raw data, derivative evidence, labels, weights
and vectors stay local. Git holds code, small fixtures and documents only.

- Summaries are not intrinsically inadequate: SemEval explicitly tests
  theme/action/outcome similarity with Wikipedia summaries. Sufficiency is
  question-specific. MF² tests finer claim understanding with transcripts and
  some video-dependent evidence; those are different tasks.
- Neither release is automatic product evidence or canonical film metadata.
  SemEval includes novels as well as films. MF² IDs are dataset-local and are
  not IMDb/Wikidata IDs. Canonical identity and per-asset rights need review.
- SemEval official splits share story texts. Check source-work IDs too before
  calling a subset story-disjoint. No release benchmark proves our two-film,
  user-question-conditioned answers help writers.
- Three MF² pairs contain identical fact/fib strings. Preserve and quarantine
  them; never silently fix labels or put false claims into evidence.
- Real subtitle files have negative counters, nonstandard fractional times,
  untimed blocks and possible transcription errors. Preserve source maps and
  mark limitations; parse success does not establish transcription quality.
- STAGE's paper does not provide downloadable raw scripts. SagaQA's linked
  repo returned 404 during the audit. MovieSum is CC BY-NC 4.0; it is not a
  cleared product source. Recheck dated availability instead of assuming.

## Evidence and evaluation discipline

Dataset changes should be reusable scripted transformations (regex for suitable
text structure; proper parsers for JSON/CSV and timestamps), not manual edits to
individual movie records. Preserve immutable raw downloads and write versioned
derivatives with explicit quarantine/error reports. This is a user requirement,
not permission to silently rewrite ambiguous source content.

Read `docs/core-architecture-and-test-gates-v1.md` before changing these layers.
Raw snapshot → source assertion → reviewed operational `Assertion` remains the
fact chain. Do not create a second live fact/graph write target.

Separate model inputs, gold labels and source passages physically. Exact source
quotes, JSON validity and citation IDs prove source visibility, not entailment,
creativity or usefulness. Track missing evidence, retrieval omissions, wrong
character attribution, unsupported interpretation and unhelpful writing advice
as different failure classes. Do not turn small provisional development scores
into release accuracy claims.

Use existing Conda development environments. Never test against the working
corpus; DB integration tests use `cinegraph_test`. No new mocks or automatic
external crawling in normal tests. Commit/push verified in-scope milestones
without routine approval; preserve unrelated user changes and local skills.

Long jobs need one retained session/process handle and durable artifacts.
Check that job rather than creating duplicate inference/download work. Respect
disk headroom: on this 16 GB machine FP16 8B weights alone approach RAM capacity,
and quantized inference can still cause swap. Do not promise runtime or model
quality without running the controlled comparison.
