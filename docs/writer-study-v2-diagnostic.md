# Writer study v2: current journey diagnostic

Status: captured locally on 2026-09-28. This is a **technical and editorial
diagnostic**, not an independent writer review or a passed product gate.

The 20 frozen v2 tasks cover 12 preselected pairs, four film-first tasks, and
four question-only tasks across the eight declared study categories. The
runner calls the current discovery and comparison API functions in a read-only
transaction against an isolated `cinegraph_eval` clone. It records the top
source-linked discovery leads and the comparison formed from the first one or
two leads. Both the database and generated review packets remain local under
`data/evaluation/writer-study-v2/`; no corpus copy or review output is in Git.

## What the capture proves

- 19/20 tasks formed and displayed a comparison; the remaining private-meeting
  question received no discovery leads. That is appropriate abstention, not a
  product error.
- Two displayed comparisons explicitly abstained: a measured audience-behavior
  request (appropriate) and a *Children of Men* / *Fury Road* protection question
  (possibly over-conservative; it needs human assessment).
- Among displayed cards, zero lacked a source URL, revision, or licence, and no
  chunk ID repeated within one film's comparison lenses.
- No semantic fallback occurred. The initial cold request took 4.57 seconds;
  subsequent requests had a median of 1.07 seconds and a maximum of 2.45
  seconds. These are sequential in-process timings, not browser task time or a
  production latency benchmark. A warmed rerun was faster, so cold-start and
  cache effects need separate measurement.

## Relevance failures to investigate

- For a film-first *Her* question about artificial companionship, the initial
  ranking put *The Grand Budapest Hotel* and *Persona* ahead of *Ex Machina*.
  A missing cue for “artificial companionship” caused generic relationship
  passages to compete. After a narrow topic-cue fix, *Ex Machina* ranks first;
  this is a development-set improvement, not held-out validation.
- A *Dark Knight* ethics prompt selected *The Empire Strikes Back* using a
  broad critical passage about heroism. A question about a safe-looking home
  selected *Fantastic Mr. Fox* and *Lethal Weapon*. These may provide usable
  contrasts, but their displayed passages do not clearly establish the asked
  mechanism. Human reviewers must judge them; “source-linked” is not enough.
- The two-sided exact-term check abstained for *Children of Men* and *Fury
  Road* on protecting a vulnerable stranger. The concept may be present under
  different words; the system must not mistake a conservative retrieval miss
  for evidence that the films lack it.

## Next gate

Give the generated local `primary-review-ready/review-packet.html` to two independent
writer/research reviewers. They should rate relevance, useful contrast,
accuracy, uncertainty, and whether each task produces a writer-owned next
step. Do not report the 14/20 usefulness gate as passed without those exports.
Because v2 has been used diagnostically to adjust one cue, a subsequent
held-out task set is required before claiming a measured improvement. A
separate browser study is still needed to measure interaction and task time.

The highest-value engineering follow-up is to improve passage relevance and
answerability on the failures above. Expanding film count or adding a larger
model has not been shown to solve them.

## September 28 follow-up: reviewable evidence and real browser checks

The interface now foregrounds one paired evidence lens for the writer's
question. Other fixed lenses remain available in a collapsed section explicitly
marked as possible context, not proof of an answer. Discovery leads are called
*candidates*, source revisions are visible, and an insufficient-evidence result
offers a way back to the question or film search without resetting the pair.
These are presentation and transparency changes, **not a retrieval-quality
improvement claim**.

The v2 capture now exposes stable chunk IDs for discovery passages and a
source-bound relevance control for each automatically selected discovery lead
and each passage in the primary comparison pair. The latest local packet is
`data/evaluation/writer-study-v2/primary-review-ready/review-packet.html`; it
contains 44 required passage labels across 20 tasks. Other displayed passages
remain available for whole-task judgment but are not part of the primary
passage-relevance metric. Two independent reviewers must export complete
reviews with distinct codes. The packet shows completion progress; a reviewer
can download an incomplete draft and resume it from the same capture later.
Drafts from a different capture are rejected. From the project root, aggregate
completed reviews with:

```sh
PYTHONPATH=backend python -m app.services.writer_study_v2 \
  --output-dir data/evaluation/writer-study-v2/primary-review-ready \
  --reviews REVIEW_A.json REVIEW_B.json
```

This command rejects missing
labels, stale packet IDs or source pointers, and incomplete task judgments rather than
quietly treating them as negative or positive. No human reviews have been
received, so no usefulness or relevance gate has passed.

The frontend also has a real-browser smoke test using the isolated integration
API and its `cinegraph_test` database. It covers search, comparison, evidence
pinning, a writer-owned decision, Markdown export, and abstention/recovery.
Run `backend/scripts/run_integration_tests.sh` first, then from `frontend/`
run `npm run test:e2e`. On machines with a system Chrome but no downloaded
Playwright browser, set `CINEGRAPH_CHROME_PATH` to that executable. These tests
never use the working corpus and do not replace an independent writer study.

## Independent AI proxy diagnosis (not the product gate)

Two read-only agent reviewers independently inspected the captured leads and
comparison passages. Both marked the same nine of 20 tasks clearly useful.
One marked two further tasks unclear, the other three; neither result is a
human-writer score. They agreed on the main failure modes:

1. The five fixed comparison lenses display unrelated production or reception
   passages even when the question is about a specific story mechanism.
2. Discovery can match a nearby theme but miss a hard premise, such as a
   *returning heir*, a *public* ethical test, or intimacy *rather than fear*.
3. Literal two-sided term matching can abstain on a plausible paraphrased
   relation, as with the protection question in V04.

The immediate design constraint is therefore not "show more evidence" or
"add a larger model". A useful answer needs two passages that actually bear
on the same writer question, plus an explicit account of how the treatments
differ. The lower-bound interface is one question, one grounded passage per
film, and a writer-owned contrast; extra lanes earn their place only when
they add relevant evidence. More hand-coded topic exceptions would overfit
this development set. Before changing retrieval ranking broadly, obtain
passage-level relevance judgments and evaluate on a new held-out packet.
