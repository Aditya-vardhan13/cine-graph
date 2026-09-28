# Writer-study v2: primary-evidence findings, 2026-09-29

Status: local development-set diagnosis, **not** independent human review or a
passed usefulness gate. The source-linked captures are local under
`data/evaluation/writer-study-v2/`; no corpus or review payload is committed.

## What the captured results show

The original 20-task packet displayed 19 comparisons and returned no leads for
one unsupported private-meeting question. Two comparisons abstained. A pair of
source pointers and a displayed comparison do not establish that the passages
answer the writing question.

The most direct failure was a section-prior mismatch. The central, free-form
writer question always used `story.writer_focus`, which selected Plot passages.
This produced plot summaries for V09 (practical versus digital creature images),
V11 (critics on artistic obsession), V15 (visual design of a chase), and V16
(critical interpretations of ambition), even though production or reception
passages existed in other lenses. For example, V09's original primary pair
described the premises of *Jurassic Park* and *Avatar*, not how their creatures
were made to appear physically present.

An unrestricted-all-sections trial was rejected: it found useful craft and
reception passages but replaced V01's plot evidence with loosely related
reviews and screenplay-development material. The narrower development trial
routes only explicit craft questions to Production and explicit critic/review
questions to Reception, preserving Plot for other writer questions. Against
the same local 20 tasks, exactly V09, V11, V15, and V16 changed their primary
passage IDs; the other primary pairs and the 19/20 display count did not change.
V09 now contrasts practical/CG compositing and animatronics with motion capture;
V11 now shows attributed critical reactions. This is a **source-role alignment
improvement**, not a measured writer-usefulness or full relevance improvement.

The remaining failures have different causes:

- V04 abstains on *Children of Men* and *Fury Road* despite a plausible
  protection-of-a-stranger question. The two-sided exact-term gate may miss
  paraphrased evidence; absence of a match is not absence of the story idea.
- V14's *Empire Strikes Back* lead concerns Vader testing carbonite and Luke's
  loyalty, but does not clearly establish the requested **public** ethical
  test. The matcher conflates nearby uses of “test.”
- V17's *Throne of Blood* passage concerns a commander's rise, not clearly a
  **returning heir**; the paired *Baahubali* passage identifies an heir but does
  not itself establish the requested loss of family. Shared monarchy terms
  do not prove the complete relation.
- V19's *Fantastic Mr. Fox* home is endangered by farmers, while the selected
  *Lethal Weapon* passage is about a suspect's exploding home. Neither pair
  clearly develops a safe-looking home becoming the protagonist's source of
  danger.
- V15's new Production pair still gives only weak evidence for **chase
  readability**, and V16's criticism concerns ambition in different senses.
  Section routing alone cannot solve passage-level relevance or contrast.
- Some retained passages contain Wikipedia image-caption markup. Cleaning that
  requires a versioned preprocessing change and re-indexing, not an in-place
  alteration to old evidence chunks.

## Next evaluation boundary

`backend/tests/fixtures/writer-study-v2-heldout.json` freezes 20 new task
questions (12 pair, four film-first, four question-only) across the same eight
categories. Their questions and selected film pairs do not duplicate the
development manifest. The 28 named films were checked only for collection
membership and eligible-chunk presence in the isolated evaluation database;
**no retrieval results were inspected for these tasks**.
This protects the set from tuning to its outputs. Film identity and passage
presence do not guarantee that the questions are answerable.

The next product gate is two independent reviewers labeling the displayed
primary passages and whole writer tasks. The review summary now reports
task-level discovery status, primary-pair status, and disagreements, and does
not count a one-lead question-first result as a successful two-film discovery.
Only after the current diagnostic is reviewed should the held-out manifest be
run once, without further task rewriting, to assess whether the change
generalizes. Any broader re-ranking or model change needs relevance labels
and a fresh evaluation set after that.
