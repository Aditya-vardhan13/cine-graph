---
name: cinegraph-narrative-research
description: Prepare or evaluate CineGraph narrative datasets and grounded model experiments, preserving source evidence, benchmark separation, and honest task-specific quality claims.
---

Read `docs/core-architecture-and-test-gates-v1.md`, then the current dated
dataset audit and experiment plan. Paths are relative to the CineGraph root.

## Decisions that must not be rediscovered

- Use scripts and parsers for repeatable dataset transformations; use regex
  where it fits the text structure. Do not hand-edit movie records or mutate
  original downloads. Write versioned derivatives and report exceptions.

- Match the task to the evidence: story summaries can support theme/action/
  outcome comparisons; dialogue attribution, scene detail and temporal claims
  may require transcripts/scripts or video. Do not infer that every failure
  needs a bigger model or a complete screenplay.
- A paper, public repository or declared collection size is not a usable
  release. Verify actual files, dates, licence scope and upstream asset rights.
  Distinguish first publication, revision and download availability.
- Keep evidence documents, user-like evaluation inputs, gold labels and invalid
  records separate. Facts/fibs are benchmark queries, not corpus evidence.
  Synthetic annotations do not become operational facts or independent gold.
- Preserve captures unchanged, hash every derivative, retain exact source
  locators/offsets, and fail rather than silently discard malformed content.
  Untimed subtitle blocks stay untimed; never invent character speakers.
- Report split overlap at both text and source-work identity levels. Official
  split names and multiple task tracks do not establish independent examples.
  Do not tune on heldout labels, reuse known test questions as training, or
  present a development score as general product quality.

## Existing tools

- `scripts/acquire_narrative_benchmarks.py --download`: explicit, bounded,
  pinned manual acquisition; not part of tests.
- `scripts/prepare_narrative_benchmarks.py --output data/evaluation/...`:
  offline, append-only research preparation and development lexical control.
- `scripts/validate_narrative_preparation.py data/evaluation/...`: checks
  hashes, source bindings, offsets, coverage, label separation and quarantine.
  A passing result is not semantic or annotation correctness.

For model comparisons, hold evidence/prompt/budgets fixed, record exact model
and quantization, separate retrieval from generation errors, and inspect cited
claims against their supporting text. Quantization/distillation needs its own
quality comparison; structured JSON or valid citation IDs are insufficient.

Use one background process for long work and retain its real process/session
handle and report path. Poll the same handle; do not restart just because output
is quiet. Report measurements after completion, not inferred from stale logs.
Check local disk/memory headroom before inference; do not modify other services
or remove valuable model/corpus data to force a run.

Keep project memory in `docs/project-memory.md` current only when requested.
Do not alter user-global configuration or unrelated skills. Follow AGENTS.md
for tests, publication, source-of-truth and local data restrictions.
