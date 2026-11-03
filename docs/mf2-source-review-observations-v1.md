# MF² diagnostic source-review observations

This is a narrow, source-aware exploratory review of the local
`mf2-lexical-dev-run1` rankings and its ten-case blind sample. It is not an
independent annotation, a measurement of accuracy, or a review of all 190
queries. Gold labels were not consulted. The underlying source text is retained
locally; no dataset record was edited.

## Concrete findings

- `mf2:7:1:b` asks whether Claude took a job to earn money to buy a house.
  The first three retrieved transcript chunks discuss money and a house but do
  not establish that motive. The film's `synopsis:0` does explicitly describe
  the job motivation; it is **sixth**, outside the three-lead review sample.
  This is a source-availability versus ranking example, not proof that a
  particular replacement ranker will improve it.
- `mf2:4:2:b` asks whether a kneeling man begs for his life. The synopsis at
  rank two describes the kneeling and plea. Rank one is dialogue from another
  part of the story and does not establish the requested event. This illustrates
  why lexical rank alone should not be presented as verified relevance.
- `mf2:15:18:a` asks whether a spacecraft landing is smooth. The inspected top
  three are about preparations, background, or restoration information, not the
  landing itself. The claim may need visual evidence; this review does not prove
  that text evidence is unavailable elsewhere in the film.
- `mf2:30:19:a` asks how a character learns of a death. Rank one describes the
  death but not the means of learning about it. Subject overlap is insufficient
  evidence for the claim's requested causal or informational detail.
- `mf2:47:1:b` names a specific person making a threat. The top synopsis
  attributes a threat to another described character, but the excerpt alone does
  not establish whether the names refer to the same person. Resolve identity
  from additional source evidence before calling the claim supported or false.

## Implications for the next controlled experiment

Freeze source-bound candidate pools before comparing rankers; include at least
the full six retained leads so source availability is not confused with top-three
visibility. Score support and contradiction separately from topical relevance,
allow insufficient evidence, and distinguish text-only from visual requirements.
Check person identity and causality rather than treating keyword overlap as
entailment. Review a broader, stratified set before drawing an aggregate quality
conclusion. No test-set or product accuracy is asserted by these examples.
