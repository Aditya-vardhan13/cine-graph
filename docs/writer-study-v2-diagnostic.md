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

Give the generated local `topic-cue-rerun/review-packet.html` to two independent
writer/research reviewers. They should rate relevance, useful contrast,
accuracy, uncertainty, and whether each task produces a writer-owned next
step. Do not report the 14/20 usefulness gate as passed without those exports.
Because v2 has been used diagnostically to adjust one cue, a subsequent
held-out task set is required before claiming a measured improvement. A
separate browser study is still needed to measure interaction and task time.

The highest-value engineering follow-up is to improve passage relevance and
answerability on the failures above. Expanding film count or adding a larger
model has not been shown to solve them.
