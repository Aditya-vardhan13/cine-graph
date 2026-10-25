# Local story-draft pilot (2026-10-25)

This is a small product acceptance check, not a benchmark. Two real English
collection comparisons used the active local evidence index and three retrieved
passages per film. The generation endpoint reloaded eligible chunks by ID and
required references from both films. Model text was never stored as an
`Assertion` or treated as a reviewed interpretation.

| Model | Her × WALL-E | Batman Begins × The Dark Knight | Decision |
| --- | --- | --- | --- |
| DeepSeek Coder V2 15.7B Q4 | Treated WALL-E's cockroach as an artificial companion and forced a human-loneliness parallel | Generic, repeated the question as a writing move | Reject as default |
| Qwen3 4B | First and second readings were only source headings; contrast claimed EVE required biological interaction | Failed the citation/completeness check | Reject as default |
| Qwen3 8B | More complete and cited, but still called EVE a route to *human* connection rather than distinguishing the robot's bond from the humans' dependence on service robots; 47.4 seconds | Conflated Bruce Wayne's public persona with Batman's public symbol, and proposed rewriting both existing films rather than an original writer's scene; 39.0 seconds | Reject as default |

These are observed local warm/cold single-request times, not p50/p95 figures.
The evidence retrieval and source attribution worked, but syntactically valid
citations did **not** guarantee that each interpretation was supported by the
cited passage. The 4B output also demonstrated that a structured JSON schema
does not establish substantive answer quality.

Therefore the AI draft is opt-in and disabled by default. The normal writer
path remains question-led retrieval, inspecting passages and sources, pinning
evidence, and authoring a comparison. An operator may explicitly enable the
experimental draft to review it. The API rejects invented reference IDs,
wrong-film references, missing contrast sides, heading-only readings, and
simple question repetition, but it cannot prove semantic entailment.

Before making generation part of the core paid flow, build a held-out set of
writer questions with reviewed passage support and human ratings for premise
handling, factual faithfulness, comparative specificity, writing usefulness,
and latency. Test a rights-compatible stronger model or an explicit user-key
provider against those cases. Do not select a model solely from size or a
retrieval benchmark.
