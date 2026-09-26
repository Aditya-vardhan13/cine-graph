# Writer-task study v1

Status: technical capture complete on 2026-09-24; independent human review is
pending. This is a product gate, not a retrieval leaderboard.

## Study contract

The committed manifest has 20 fresh writer tasks across character change,
moral dilemma, plot structure, worldbuilding, craft, genre inversion, reception
disagreement, and deliberately unanswerable requests. Sixteen start with two
films, two start with one film, and two start only with a writing problem.
These entry modes are part of the test, not quietly converted into pair tasks.

The local runner invokes the actual comparison API function in a read-only
PostgreSQL transaction and saves its user-visible response. It does not crawl
external sources, change the corpus, or assign usefulness scores. The HTML
packet presents the same question, five lenses, evidence excerpts, and source
links reviewers would inspect on the current board. It is an evaluation view,
not a browser-interaction or accessibility test of the Next.js UI.

## Technical capture

On the current local 1,000-film research collection and recovered Qwen3
Embedding 0.6B index:

| Observation | Result |
| --- | ---: |
| Pair tasks displayed | 16/16 |
| Film-first and question-only tasks unsupported | 4/4 |
| Evidence cards displayed | 160/160 |
| Cards lacking URL, source revision, or licence | 0 |
| Repeated chunk IDs within a film's five lenses | 0 |
| Semantic fallback requests | 0 |
| First request in initial cold capture | 1,627 ms |
| Subsequent request median in refreshed packet | 429 ms |
| Subsequent request maximum in refreshed packet | 521 ms |

These are sequential, local API-function timings, not end-to-end browser task
times or production latency targets. They do not establish relevance,
accuracy, novelty, or whether a writer reached a decision.
The refreshed local report pins manifest SHA-256
`20af4c445226598f0bec095915e44bcbba823ef2e726b2735a54185938d673c9`
and the index run used by each comparison.

Two unanswerable pair prompts (`W15`, `W16`) still received ten populated cards
each and the summary "5 evidence lenses are ready for side-by-side analysis."
The product has no explicit insufficient-evidence/abstention state. A manual
spot-check also found plausible but question-weak cards, including a *Black
Swan* reception card about a cast photo and a *Blade Runner 2049* reception
card not directly about the requested everyday-routine worldbuilding. Human
review must judge these and the rest; no benchmark labels or ranking policy
were changed in response.

## Independent review protocol

Open the local `data/evaluation/writer-study-v1/review-packet.html` separately
with two independent writer or film-research reviewers. Each reviewer enters a
different anonymous code, rates every task, records time spent, writes evidence
and decision notes, and downloads their own JSON. Reviewers should not discuss
tasks until both exports are complete. The packet has no network submission.

For each task, judge usefulness, relevance, evidence accuracy, useful contrast,
non-obviousness, uncertainty handling, a writer-owned next step, unsupported
claims, and appropriate abstention. An unsupported entry flow should be scored
as the product failing that task, not skipped. "Unclear" is allowed, but it
cannot count as a successful safety judgment. Do not equate a linked source
with a relevant or sufficient answer.

After both reviewers export their files, keep them local and run:

```bash
PYTHONPATH=backend /Users/vkammela/opt/anaconda3/envs/cine-graph/bin/python \
  -m app.services.writer_study \
  --reviews /path/to/writer-study-review-a.json /path/to/writer-study-review-b.json
```

The read-only review aggregator requires complete, distinct reviews and reports
the declared gate: both reviewers find at least 14/20 tasks useful, neither
finds an unsupported claim, and both confirm abstention on unanswerable tasks.
Its summary stays local under `data/evaluation/writer-study-v1/`. Until those
reviews exist, the gate is **not passed**. The current product is also missing
film discovery and abstention, so those are the first likely fixes to test,
not a reason to expand the corpus or add generated conclusions yet.
