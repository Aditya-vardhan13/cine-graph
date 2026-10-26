# Question-specific pair relevance gate (development set)

## Why this gate exists

The live Endgame × Godfather question exposed a category error: two source-linked
passages, or five filled comparison lenses, do not imply that either passage
answers the writer's question. A 200 response, a high vector score, and a film
title match are not correctness signals.

The irreducible product requirement is one answer-bearing source passage per
film for the *same* question. Thus the theoretical ceiling is the fraction of
questions for which both films have at least one answer-bearing passage in the
retained corpus. If that ceiling is below 80%, changing model size cannot meet
the goal; we must improve sources, question routing, or honest abstention.

## Frozen development questions

`backend/tests/fixtures/pair-relevance-50-v1.json` defines ten film pairs and
five distinct questions for each. The first question preserves the user's
Endgame × Godfather wording. Plot, character, craft, and reception/legacy
questions are represented. The questions were frozen before inspecting this
capture's rankings, but their passages have now been inspected during
development, so **this is not a held-out set**.

The read-only capture tool runs only against local `cinegraph_eval`. It saves
source-linked candidates and timing under ignored `data/evaluation/` and
refuses to report an accuracy number without explicit passage labels. No live
source calls, corpus writes, or mock frameworks are involved.

## Relevance rubric and metrics

For each candidate, a reviewer reads the *question and passage*, without the
ranking method or its score, and records:

- `1`: the passage directly supports at least one necessary event, choice,
  technique, or attributed interpretation requested by the question, with
  enough context that a writer can explain the connection **or a meaningful
  contrast that challenges the question's premise**;
- `0`: the passage only shares a broad subject, person, genre, or keyword; is
  about a different part of the film; or is too ambiguous to support a claim.

The primary metric is **pair success@1**: both first displayed passages are
relevant for the same question. A question succeeds only if *both* sides do.
The requested 80% gate therefore means at least 40 of 50 questions. Secondary
metrics are side precision@1 (out of 100 film-question sides), oracle
coverage@10 (whether any candidate in each side's pool is relevant), abstention
correctness, and p50/p95 warm latency. Score labels are keyed to immutable
chunk IDs; absent labels invalidate the score, not count as zero.

Reranker scores are **not** human labels. We compare baseline hybrid ranking,
Qwen3-Reranker-0.6B, and—if the local machine can safely run it—a quantized
Qwen3-Reranker-4B using the same captured candidate pools. A larger model is
promoted only if it improves reviewed pair success and is workable at the
pilot's latency and memory budget. A fresh pair set must validate any
development-set tuning before a broad quality claim.

The 4B local trial uses the [Apple-Silicon 4-bit MLX conversion](https://huggingface.co/soichisumi/qwen3-reranker-4b-mlx-4bit)
of the [official `Qwen/Qwen3-Reranker-4B` model](https://huggingface.co/Qwen/Qwen3-Reranker-4B) (conversion commit
`f9f609de317b9b24bdf75d2d7f0d535337e5dd79`), pinned locally under ignored
`data/models/`; the model and `mlx-lm==0.31.3` environment are not Git assets.
The conversion's own model card reports a small ranking-quality loss versus
the original model, so this trial does **not** establish full-precision 4B
quality. The first warm case took about 38 seconds for both film sides on the
local Mac, too slow to silently put in the live API. The model trials run
serially, checkpoint each completed case, and refuse to continue below 6 GiB
free disk.

## Local development results (2026-10-26)

All methods used the same 50 captured questions and top-10 candidate pools.
Title-aware query text was `Film: <title>\nResearch question: <question>`. The
evidence-first instruction additionally emphasized concrete, question-bearing
events, choices, consequences, craft or attributed reception evidence. The
instruction is configurable only in the offline MLX trial. RRF is also an
offline diagnostic, not the live retrieval path.

| Method | Pair success@1 | Side precision@1 | Warm local p50 / p95 per two-film question |
| --- | ---: | ---: | ---: |
| Hybrid retrieval | 31/50 (62%) | 78% | — |
| Qwen3-Reranker-0.6B | 32/50 (64%) | 79% | 8.7 / 48.4 s |
| 0.6B with film + source-section context | 33/50 (66%) | 81% | 7.9 / 24.1 s |
| Quantized Qwen3-Reranker-4B | 35/50 (70%) | 83% | 18.6 / 53.0 s |
| 4B with film title | 37/50 (74%) | 85% | 19.1 / 55.2 s |
| 4B, title + evidence-first instruction | 38/50 (76%) | 86% | 26.9 / 78.9 s |
| 4B, title + film/section passage context | 38/50 (76%) | 86% | 21.5 / 58.8 s |
| 4B, both compared titles + film/section context | 33/50 (66%) | 81% | 21.2 / 60.6 s |
| Four-source reciprocal-rank fusion | 35/50 (70%) | 83% | — |
| BAAI/bge-reranker-v2-m3, title + section context | 26/50 (52%) | 73% | 2.5 / 6.3 s |
| Qwen 4B + BGE reciprocal-rank fusion | 32/50 (64%) | 80% | — |

The 4B title/evidence-first and film/section-context variants tie for best
single ranking at 38/50 (76%). Source-section context reduced the measured
4B p50/p95 from 26.9/78.9 seconds to 21.5/58.8 seconds, but is still far too
slow for an inline local request. Adding the *other* film title to each side's
query regressed to 33/50 (66%); do not assume pair context helps a per-film
relevance judgment. None of these trials justify replacing the 0.6B path in
production. A diagnostic union of top-ranked passages from the tested models
could cover 42/50 questions (84% oracle); this is not a usable selector and
cannot be treated as achieved accuracy. The judged top-10 pools contain
relevant passages for both sides in 45/50 questions, so five questions have at
least one side not covered by the current candidate pool.

Further offline selector checks did not pass the gate: selecting a model by
broad evidence intent or question position scored 39/50 (78%) under
leave-one-film-pair-out evaluation; score-margin selection and normalized
score blending did not beat the 38/50 single-model result. Choosing a model
per intent using all ten pairs reaches 40/50, but that is an in-sample result
on the same labels and is rejected as overfit, not counted as a pass.

A separate prior retrieval experiment is a useful lead, not a comparable score:
on 11 narrative queries, Qwen3-Embedding-4B film-scoped/section-routed
candidates followed by Qwen3-Reranker-0.6B achieved MRR@10 1.0 and recall@10
1.0; the question-only candidate method had MRR@10 0.6091. Its target chunks
and evaluation questions differ from this 50-question pair benchmark, so those
metrics cannot be substituted here. It motivated testing explicit film and
source-section context with the smaller reranker. A project-local ignored
Python dependency overlay resolved the NumPy/PyTorch ABI mismatch without
changing the Conda environment or using the unsafe duplicate-OpenMP workaround.
The 0.6B context-aware result is included in the table above. A fresh local
Ollama 0.6B capture was regenerated and matched the earlier hybrid capture in
99 of 100 film-side pools; reranking it with 4B again scored 38/50 (76%). A
hybrid/lexical candidate union added 32 distinct passages across those pools
and was also reranked at 38/50. Neither changed the best result.

Further candidate/model checks did not improve the gate. Increasing the hybrid
retrieval candidate limit from 30 to 100 introduced only two additional unique
passages in this fixed study and did not change baseline pair success (31/50).
Reranking the hybrid/lexical/semantic candidate union with the existing Qwen 4B
configuration also stayed at 38/50 (76%). A local run of
[BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3),
with each candidate prefixed by film title and source section, took 2.5/6.3 s
warm p50/p95 but scored 26/50 (52%) on this development set. Its new top
choices were labeled after the model output was known, so this is an
unblinded exploratory result, not a fair head-to-head estimate. Reciprocal-rank
fusion of BGE and Qwen 4B scored 32/50 (64%) on the same exploratory labels and
was discarded.

The newly retrieved Jurassic Park water-ripple passage was then added to the
P04-Q4 candidate pool and reranked with the same Qwen 4B configuration. It was
ranked 10th on the Jurassic Park side (33.4 seconds for that side), despite
being manually judged directly relevant. This one-case diagnostic is not a
benchmark score, but it confirms the current limitation is not only candidate
recall: the strongest reranker can still bury highly specific evidence in a
broader pool.

A separate Qwen3-Embedding-4B cosine reranker over 96 previously reviewed
candidates took about 956 seconds and scored 34/50 (68%), with 81% side
precision. This was candidate reranking, not a full-corpus embedding/retrieval
trial, and it did not justify replacing the current embedding index. The 4B
cross-encoder remains the strongest tested ranking at 38/50, but has not passed
the 40/50 gate. No model or fusion result is being promoted to production.

One additional global, answer-bearing instruction was tested on the same
hybrid/lexical union and the same 50 questions. It distinguished plot evidence
(events, choices, causes and consequences), craft evidence (production
decisions and effects), and attributed reception evidence, while penalizing
broad topical overlap. It changed 13 of 100 selected passages, but after
separately reviewing (non-blindly) its eight previously unseen selections, it
scored 38/50 (76%) and 86% side precision—the same aggregate as the prior 4B
instruction.
Warm local p50/p95 were 21.4/66.3 seconds per two-film question (prior
instruction on that union: 19.9/64.5 seconds). This prompt change is not an
improvement and should not be promoted. The local ranking output and the eight
additive review judgments remain under ignored `data/`.

Labels are one reviewer's exploratory 0/1 judgments on this development set.
No independent second reviewer or held-out validation set has been used. The
best score is therefore 38/50, **not** evidence that the general product is at
76% relevance, and certainly not a pass. The fresh Ollama capture and all
ranking results remain local under ignored `data/`.

The MLX reranker initially used its default 12 GiB working-set budget and
exhausted disk headroom while the evaluation-only Ollama container also held
its embedding model. Unloading that temporary container and capping MLX at
4 GiB with a 512 MiB cache allowed the complete reranking pass while retaining
the existing 6 GiB free-disk guard. The temporary container is now stopped.
Later trials temporarily lowered the explicit guard to 4.5 GiB; no further
large model should be downloaded on this nearly full local disk. In particular,
do not infer that a larger model will improve this benchmark: the 4B and BGE
results show model size alone is not a reliable fix.

The local review packet removes model names and scores and sorts candidate
chunk IDs deterministically. A separate hand-reviewed 0/1 sequence is bound
to the packet fingerprint; stale rankings and missing labels fail closed.

## Reproduction

Use the project API image with a bind mount of `backend/`, set
`DATABASE_URL` to `cinegraph_eval` and `PYTHONPATH=/app`, then run:

```sh
python -m app.services.pair_relevance_eval \
  /app/tests/fixtures/pair-relevance-50-v1.json \
  --output /app/data/evaluation/pair-relevance-50/baseline-hybrid-routed.json
```

The local `data/evaluation/` mount is required for the output. The capture
includes the UI's top three focus options and ten film-scoped candidates for
reranker trials. It raises if a requested hybrid run silently degrades to
lexical retrieval.

In the project API Python environment, after capture, run the 0.6B CrossEncoder
and 4B MLX trial separately against the *same* capture. Both accept `--resume`
for a matching checkpoint and stop when free disk drops below 6 GiB. Then
create a blinded review packet from complete ranking files:

```sh
PYTHONPATH=backend python -m app.services.pair_relevance_review \
  data/evaluation/pair-relevance-50/baseline-hybrid-routed.json \
  --ranking data/evaluation/pair-relevance-50/rerank-0.6b-routed.json \
  --ranking data/evaluation/pair-relevance-50/rerank-4b-film-title.json \
  --ranking data/evaluation/pair-relevance-50/rerank-4b-film-section.json \
  --ranking data/evaluation/pair-relevance-50/rerank-4b-pair-context.json \
  --output data/evaluation/pair-relevance-50/review-packet.json
```

The controlled 4B context comparison uses the same pinned local MLX model,
instruction, candidate capture and top-10 pools; only query/document context
changes:

```sh
PYTHONPATH=backend data/venvs/mlx-reranker/bin/python -m app.services.pair_mlx_reranker_trial \
  data/evaluation/pair-relevance-50/baseline-hybrid-routed.json \
  --output data/evaluation/pair-relevance-50/rerank-4b-film-section.json \
  --model data/models/qwen3-reranker-4b-mlx-4bit --max-cases 50 \
  --include-film-title --include-film-context \
  --instruction 'Rank evidence only when the passage directly supports the research question for this specific film. Prefer concrete events, choices, causal consequences, craft decisions, and attributed reception. Penalize broad topical overlap and unsupported inference.'
```

Add `--include-pair-context` to reproduce the comparison-partner variant.

The packet and its reviewed label sequences stay under ignored `data/`; only
the 50 questions and evaluator code are versioned in Git.

## Open risks

- Some questions may assert a premise not well evidenced in one film. A
  reviewer must mark that separately; no model should invent supporting text.
- Current chunks average hundreds of tokens and often cover several plot
  beats. Even a relevant chunk may read like a random plot dump on screen.
- Production and reception section routing is partly keyword-based. It may
  select an unrelated section or miss an answer expressed without the cue.
- The live comparison now shows only the writer's central question. A returned
  source lead is still not a relevance verdict; this gate decides whether a
  reranker can improve the first displayed passage on both sides.
