# Embedding and retrieval decision v1

## Decision

CineGraph will not use a single embedding score as its intelligence layer.
The system needs four separate candidate sources:

1. structured assertions for objective facts and declared work relationships;
2. PostgreSQL full-text / BM25-style lexical retrieval for titles, people,
   awards, terminology, and exact phrasing;
3. semantic retrieval over licensed `EvidenceChunk` rows for passages that a
   writer should inspect; and
4. source-backed narrative profiles for events, roles, relationships, stakes,
   setting, and formal structure.

The latter is a reviewable extraction workflow, not a vector-generated label.
Cross-film story comparison may use semantic retrieval to nominate evidence,
but must compare those explicit profile fields before it makes a useful claim.

## Routing rule

`route_research_question` is the pure policy boundary between the question
catalog and retrieval. It routes source facts to `Assertion` first, narrative
extraction to semantic evidence with lexical fallback, and interpretation to
an attributed criticism corpus. An unclassified question starts with lexical
evidence. This prevents a dense match from impersonating a fact and prevents
the narrative benchmark from being judged by questions whose evidence is not
in its corpus.

## Selected local model and retrieval path

Use `qwen3-embedding:0.6b` through local Ollama for the first persisted index.
Its 32k context window prevents the 512-token truncation failure found in the
rejected BGE-small run. The adapter sets
`truncate: false` anyway: a model limit is never permission to silently lose
evidence.

Qwen receives an explicit retrieval instruction that asks for direct,
source-backed evidence. Documents stay verbatim except for their independently
versioned chunk representation. The local API process does not import model
weights; the offline worker and retrieval adapter call Ollama through a narrow
vector-only port.

The selected request path is:

1. resolve the film as structured identity;
2. route the declared research-question kind;
3. apply a deterministic section prior when one exists;
4. embed the question locally;
5. rank only source-linked chunks for that film and route in pgvector; and
6. return the passage, section, source snapshot, score, and candidate label.

All 24,194 eligible chunks are now present in the completed local index run.
`python -m app.services.local_retrieval_status` is the read-only trigger for
checking index completion and unfinished checkpoint files.

## Required benchmark before selection

The existing 44 cited research answers form a regression seed, not a sufficient
benchmark. The next local manifest must curate 200 questions with exact source
passage targets, at least 40 each for:

- plot/event and character relationship;
- production/craft;
- reception/cultural legacy;
- objective fact lookup routed through the structured/lexical path; and
- cross-film comparison or contrast.

Each category needs adversarial near-neighbours and a held-out test partition.
Report Recall@10, MRR@10, evidence provenance success, p50/p95 query latency,
offline documents/second, memory, and zero-truncation status. Evaluate BM25,
dense, their reciprocal-rank fusion, and a reranker separately.

## Deferred candidate

`BAAI/bge-m3` is the future multilingual/hybrid option because it can produce
dense, sparse and late-interaction representations. It is deliberately not
run on this 16 GB CPU-only machine yet. Its model size and the prior 2.4-hour
BGE-small build make it an infrastructure decision, not a casual upgrade.

Qwen 4B is also deferred. It materially improves unfiltered dense ranking, but
once CineGraph's known film and declared section route are applied it gives no
quality gain over 0.6B while building about eight times more slowly in the
controlled local benchmark. The official 0.6B reranker is rejected for v1
because its measured quality gain was negligible and its latency was seconds,
not milliseconds.

## Research basis

- [Qwen3 Embedding 4B model card](https://huggingface.co/Qwen/Qwen3-Embedding-4B)
  documents the 32k context, 2,560 native dimensions, MRL support, multilingual
  scope, and instruction-aware retrieval.
- [Qwen3 Reranker 0.6B model card](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)
  provides the official CrossEncoder usage and reports reranking over dense
  top-100 candidates. CineGraph measured it locally before rejecting it.
- [AIStorySimilarity](https://aclanthology.org/2024.conll-1.13/) supports
  decomposing story comparison into explicit elements rather than treating one
  whole-plot cosine score as explanation.
- [Event and social relationship story retrieval](https://aclanthology.org/N18-2106/)
  reports gains from structured event and relationship signals over a plain IR
  baseline. That supports CineGraph's future narrative-profile layer after
  candidate passage retrieval.
