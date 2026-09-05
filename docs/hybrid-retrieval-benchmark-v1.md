# Hybrid retrieval benchmark v1

Status: local quality gate implemented and passed on 2026-09-06.

## What this proves

CineGraph can retrieve source-linked evidence for a known film and a declared
research intent with useful local latency. The system routes objective facts
to reviewed `Assertion` rows and narrative questions to eligible,
source-snapshot-linked `EvidenceChunk` rows. A semantic result remains a
candidate; it cannot publish a fact or graph edge.

This gate does **not** yet prove answer synthesis, open-ended film discovery,
or a writer-facing comparison. The cross-film cases independently retrieve
supporting evidence for both films; the next intelligence layer must compare
those passages without erasing disagreement or provenance.

## Benchmark contract

The committed manifest contains 200 questions and no copied source prose:

| Category | Development | Held out | Total |
| --- | ---: | ---: | ---: |
| Plot, character, and structure | 10 | 30 | 40 |
| Production and craft | 10 | 30 | 40 |
| Reception and legacy | 10 | 30 | 40 |
| Objective facts | 10 | 30 | 40 |
| Cross-film comparison | 10 | 30 | 40 |

Every narrative target records a film QID, exact source revision, section
locator, and SHA-256 passage hash. Every structured target records a reviewed
assertion fingerprint. Manifest construction also requires narrative targets
to have an eligible chunk in the versioned v3 preprocessing run. The gold set
was evidence-reviewed by the assistant and remains explicitly marked
`human_review_required`; it is not presented as independent expert annotation.

Twenty cases in each single-film narrative/fact category use an indirect
paraphrase, and all 40 cross-film cases require evidence from two independently
ranked film scopes. Development and test contain 10/30 cases per category, so
the held-out score is not dominated by one task type.

## Retrieval policy

1. Resolve film identity by canonical entity/QID.
2. Route known intent before ranking: plot/structure, production/craft, or
   reception/legacy. Objective facts never enter semantic retrieval.
3. Rank eligible evidence with persisted Qwen3 Embedding 0.6B vectors in local
   PostgreSQL/pgvector.
4. Rank sparse candidates with PostgreSQL full-text search using a safe OR
   query over content terms.
5. Fuse ranks with weighted reciprocal-rank fusion (`k=60`, semantic weight
   `3`, lexical weight `1`). Scores from unlike rankers are never treated as
   directly comparable.

The 3:1 fusion and intent routing were selected only against the 50-case
development split. The 150-case test split was then evaluated with the policy
frozen.

## Results

`Recall@10` counts whether every evidence target is represented. For a
cross-film case, complete recall requires at least one gold passage from each
film's separate ranking. `MRR@10` rewards placing that evidence near the top.

| Split and method | Cases | Target recall@10 | Complete-case recall@10 | MRR@10 |
| --- | ---: | ---: | ---: | ---: |
| Development system | 50 | 1.000 | 1.000 | 0.735 |
| Held-out system | 150 | 1.000 | 1.000 | 0.845 |
| Held-out hybrid narrative | 120 | 1.000 | 1.000 | 0.806 |
| Held-out dense-only narrative | 120 | 0.992 | 0.992 | 0.782 |
| Held-out lexical-only narrative | 120 | 0.850 | 0.808 | 0.399 |
| Held-out structured facts | 30 | 1.000 | 1.000 | 1.000 |

Held-out system results by category:

| Category | Recall@10 | MRR@10 |
| --- | ---: | ---: |
| Plot, character, and structure | 1.000 | 0.861 |
| Production and craft | 1.000 | 0.879 |
| Reception and legacy | 1.000 | 0.758 |
| Objective facts | 1.000 | 1.000 |
| Cross-film comparison | 1.000 | 0.726 |

On the held-out run, batched local query embedding averaged 101 ms per
question. Hybrid PostgreSQL ranking measured 13 ms p50 and 38 ms p95. These are
local measurements, not production SLOs.

The acceptance gate requires overall target recall of at least 0.90, overall
MRR of at least 0.70, and at least 0.85 target recall in every category. Both
splits pass. Every returned benchmark result retained a source pointer.

## Known debt kept visible

The 1,000-film narrative collection has full narrative identities, but only
128 entities (12.8%) currently overlap the legacy `Film` projection and have
reviewed `Assertion` rows. Objective-fact cases therefore use an honest
40-film subset of that intersection. This benchmark does not claim 1,000-film
structured coverage and semantic retrieval does not fill that gap.

The next data task is an additive projector from retained source assertions to
the existing `Assertion` operational projection. It must not introduce a
second live fact source.

## Reproduce locally

Raw source data, embeddings, database volumes, model weights, and generated
reports remain outside Git.

```bash
conda activate cine-graph
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/cinegraph \
  PYTHONPATH=backend python -m app.services.retrieval_benchmark_v1

DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/cinegraph \
  PYTHONPATH=backend python -m app.services.retrieval_benchmark_runner --split development

DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/cinegraph \
  PYTHONPATH=backend python -m app.services.retrieval_benchmark_runner --split test
```

The runner writes self-contained JSON and HTML reports under
`data/evaluation/retrieval-benchmark-v1/`. That directory is local-only by
policy.
