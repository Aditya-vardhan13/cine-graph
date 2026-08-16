# CineGraph core architecture and test gates (v1)

## Decision

Before corpus preprocessing, retrieval, or embeddings, CineGraph has one
non-negotiable design goal: adding a source, language, model, or collection
must be additive. It must not require changing unrelated HTTP handlers,
canonical fact rules, or stored evidence.

"SOLID" is not a goal by itself. The useful result is a small number of
stable boundaries around the places that genuinely change independently.
Generic repositories, factories, and interfaces for every ORM table are not
permitted; they would add indirection without reducing change.

## Stable layers

```
HTTP controller
    -> application use case
        -> domain policy
            -> query / persistence port
                -> SQLAlchemy, source API, or local model adapter
```

### 1. HTTP controllers

Controllers validate request shape, call one use case, and serialize its
response. They do not contain query plans, graph scoring, or data-normalising
rules.

### 2. Application use cases

Use cases coordinate a request such as `search_catalog`, `compare_films`,
`trace_lineage`, `build_evidence_chunks`, or `retrieve_evidence`. They own
transaction boundaries and return application DTOs. Their dependencies are
explicit query, store, or adapter ports.

### 3. Domain policies

Deterministic rules live as pure functions: identity resolution ranking,
typed-relation eligibility, evidence visibility, chunk eligibility, and score
fusion. A policy receives values and returns values; it does not open a
database session, read environment variables, or call the network.

### 4. Infrastructure adapters

SQLAlchemy query services, source clients, snapshot storage, and local
embedding services implement narrow ports used by the application layer.
Source adapters return captured source payloads; they never decide canonical
truth. Model adapters return candidate rankings; they never publish facts.

## Source-of-truth rules

| Concern | Authoritative record | Rule |
| --- | --- | --- |
| Raw source payload | `SourceSnapshot` | Immutable, attributable, licence-scoped. |
| Extracted source statement | `SourceAssertion` | Replayable interpretation of one snapshot. |
| Published typed fact / graph edge | `Assertion` | Current operational projection; requires evidence and review state. |
| Narrative prose | `NarrativePassage` | Contextual evidence, never a canonical fact. |
| Embeddable derivative | future `EvidenceChunk` | Derived only from eligible narrative prose; records source, rights, chunker and model lineage. |
| Semantic relation | future `SemanticCandidateRelation` | Candidate only until separately reviewed; never substitutes for a typed edge. |

The currently unused `Claim` and `FilmRelationship` tables are not new write
targets. A future consolidation must be a documented migration, never a
second live graph.

## Change rules

- A new language supplies language configuration and an adapter; it does not
  alter English extraction rules.
- A new source supplies an access-policy record, adapter, raw snapshot, and
  mapping policy; it does not alter existing source facts.
- A new embedding model creates a new model/version record and a new index
  run. Existing vectors remain reproducible until deliberately retired.
- Read APIs depend on query-use cases, not an ORM entity shape. Schema changes
  therefore do not automatically become public API changes.
- Database migrations are additive and reversible where PostgreSQL permits.
  Application replicas must not compete to run migrations in a future
  deployment; migration execution becomes a single explicit job. Local
  startup migration remains a development convenience only.

## Test policy: real components, no mock framework

The test suite uses three complementary levels.

| Level | What is real | What is deliberately absent | Purpose |
| --- | --- | --- | --- |
| Unit | Pure domain policy and recorded source payload fixtures | Database, network, mock/patch framework | Prove deterministic rules cheaply. |
| PostgreSQL integration | PostgreSQL + pgvector, Alembic migrations, SQLAlchemy queries and transactions | SQLite substitution, network, mock/patch framework | Prove constraints, indexes, migrations and persistence semantics. |
| API contract / local E2E | Real FastAPI app, real PostgreSQL test database, HTTP response serialization | Production data mutation, external network, mock/patch framework | Prove status codes, response schemas, provenance and query behaviour. |

External-source behaviour is tested in two separate ways:

1. Normal CI/local tests replay retained, versioned source snapshots. These
   are real payloads captured under the source policy, not invented response
   objects or mocked HTTP calls.
2. A manually invoked, rate-limited `live-contract` check makes a minimal
   permitted request to each source and verifies its adapter against the live
   contract. It never runs per pull request and never writes the production
   corpus.

No `monkeypatch`, `unittest.mock`, `Mock`, `MagicMock`, or fake HTTP server is
permitted in new tests. Existing uses are technical debt and must be removed
before the preprocessing gate is declared complete.

## Required gates before embeddings

1. The full test suite has no SQLite database path for persistence behaviour
   and no mock/patch framework usage. Persistence-level tests run in isolated
   schemas inside `cinegraph_test`, while pure-policy tests remain database-free.
2. A clean local PostgreSQL test database migrates from revision zero to
   `head`.
3. API contract tests exercise `/health`, `/api/v1/health`, title search,
   a film detail response, comparison, and lineage against real seeded rows.
4. Every displayed fact or narrative result in those tests has retained source
   provenance.
5. A query-count and latency baseline is recorded for the hot endpoints.
6. Only after the above passes may preprocessing create `EvidenceChunk` rows;
   only after its quality gate passes may a local embedding model be started.

## Local baseline before embeddings (2026-08-16)

Measured against the local Docker API and PostgreSQL corpus (1,226 films; the
explicit preprocessing collection contains 1,000 films). These are single warm
local measurements, not production SLOs; they establish a regression point for
the current query plans:

| Endpoint | HTTP status | Wall time |
| --- | ---: | ---: |
| `/api/v1/health` | 200 | 92 ms |
| title search (`harry potter`, limit 7) | 200 | 13 ms |
| film detail | 200 | 47 ms |
| comparison | 200 | 16 ms |
| lineage | 200 | 19 ms |

The first vector-retrieval implementation must repeat this measurement with a
fixed query set and report p50/p95 separately from these baseline endpoints.
