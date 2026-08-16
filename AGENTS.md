# CineGraph project memory

Read [docs/core-architecture-and-test-gates-v1.md](docs/core-architecture-and-test-gates-v1.md)
before changing corpus, intelligence, retrieval, or test infrastructure.

Non-negotiable rules:

- Keep raw data, database volumes, model weights, embeddings, and snapshots local.
  Git contains code, migrations, documents, and small test fixtures only.
- Preserve the evidence chain: immutable source snapshot → source assertion →
  reviewed operational assertion. Narrative text and semantic output are never
  silently promoted to facts.
- Do not add a second live graph/fact source. `Assertion` is the current
  operational typed-fact projection; `Claim` and `FilmRelationship` are not
  new write targets.
- Prefer additive, versioned schema and adapters. Do not use a generic
  repository/factory pattern merely to claim SOLID compliance.
- Never use mock/patch frameworks for new tests. Use pure policies, retained
  source fixtures, real local PostgreSQL/pgvector, and a separate local API
  integration stack.
- Never test against or truncate the working corpus database. Integration
  tests use only `cinegraph_test`.
- No external-source crawling in normal test runs. Live source contract checks
  are explicit, rate-limited manual actions.
- Ask the user before each commit. Do not commit user-local `.agents/` or
  `.codex/` content.
