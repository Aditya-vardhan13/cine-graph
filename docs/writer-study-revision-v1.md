# Writer-study revision after the 20-task proxy review

The frozen v1 task packet and the local two-agent proxy assessment remain unchanged.
Both proxy reviewers found 10/20 tasks useful (below the 14/20 gate). Both found
the two unanswerable prompts misleadingly populated and all four film-first or
question-only tasks unsupported. This is not independent human-writer validation.

## Implemented response

- A question can now discover a small list of films before a pair is selected.
  Each candidate displays a source-linked passage, section, and licence. Search
  uses the pinned local narrative index when available, with term reranking
  inside its semantic shortlist; lexical retrieval is an explicit degraded
  fallback. Topic-cue filters remove some obvious false positives. A suggested
  film is a research lead, never a proven relationship.
- Questions requiring unavailable primary records or quantified audience
  behavior, or finding no two-sided passage lead, now produce an explicit
  insufficient-evidence result with no lens cards. This is a narrow
  source-capability and retrieval-coverage rule, not a general answerability
  model; other irrelevant passages can still be returned and need review.
- Before generic comparison lenses run, the selected films must have at least
  one direct source-term lead for the writer's original question after title
  and comparison boilerplate are removed. This prevents lens templates from
  manufacturing apparent evidence for a completely unmatched question. It is
  deliberately conservative and can miss a valid paraphrase; abstention says
  the current passages do not directly match, not that the film lacks the idea.
- A writer can pin the exact passages they used for each film, then record
  each film's mechanism, the contrast they see, and an original creative move.
  Saving requires at least one pinned source per film. Notes stay in browser
  local storage and export as JSON with film identifiers and selected chunk,
  source URL, and source revision pointers. They are writer interpretations,
  never film facts or writes to the operational assertion graph.
- Isolated PostgreSQL/API tests cover the new routes and abstention state.
  The test API uses loopback port 18001 to avoid a local process occupying
  port 8001; it still uses only `cinegraph_test`.

## Still not established

The original 20-task score has **not** improved merely because these controls
exist. Full-catalog discovery ranking, browser task time, evidence relevance,
and whether saved notes help a writer make a better decision still require a
fresh held-out task set and independent human review. The full working-corpus
live check was blocked in this revision, so no catalog-wide quality claim is
made. The comparison lenses are still candidate evidence, not synthesized
mechanism-and-difference answers. This revision does not pass the product gate.

Next evaluation: prepare fresh film-first/question-first and unanswerable
tasks, verify source relevance and first-use latency on the full catalog,
then ask two independent writers to study displayed results and saved notes.

## Scale boundary, not premature scale infrastructure

The present request contract bounds discovery to at most 12 film leads and a
fixed semantic candidate shortlist (350 passages). Comparison retrieves a
fixed number of passages for two selected films. These bounds keep response
payload and application-side work independent of whether the catalog has
1,000 or 100,000 films. They do **not** prove database latency or index size
will stay acceptable at 100,000 films. The lexical fallback can still require
a broad full-text scan until an indexed text-search path is measured and added.

Before a larger import, benchmark p50/p95 latency and query plans on an
isolated representative corpus, then add an expression GIN index or a
different retrieval adapter only if measured plans require it. Likewise,
measure the vector index's filtered recall and storage before partitioning or
introducing another service. No new database, queue, or large reranker is
needed merely to claim future readiness.

## Local reranker spike (not adopted)

An exploratory CPU run scored the frozen study packet's 160 displayed
question-passage pairs with
[`ms-marco-MiniLM-L6-v2`](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2),
a model trained for general passage ranking. Scoring took about 17 seconds
including model load. On task W09 it ranked an unrelated *Fury Road* filming
schedule as the best passage on that side. Scores also did not cleanly
separate the proxy reviewers' useful and weak tasks. This is a small diagnostic,
not a new benchmark score; the model was **not** added to the API. Any future
reranker must beat a held-out writer-evidence relevance set at acceptable
local latency before becoming a dependency.
