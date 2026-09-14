# Evidence-backed story comparison v1

## Outcome

The first writer-facing intelligence slice is a two-film evidence workbench.
A writer chooses two titles from the retained English-1,000 research corpus,
asks a concrete writing question, and receives five side-by-side lenses:

1. central question;
2. story engine;
3. character change;
4. craft treatment; and
5. reception and legacy.

Each result contains the exact retained passage, source revision, licence, and
attribution URL. The center column contains a question for the writer, not an
automatically asserted conclusion.

## Boundaries

- Search uses `CanonicalEntity` membership in
  `english-1000-retained-narrative-v1`. A legacy `Film` profile is optional, so
  all retained research films remain discoverable.
- Hybrid retrieval uses the persisted Qwen3 Embedding 0.6B index and PostgreSQL
  full-text search. The five query embeddings are sent in one local batch and
  reused for both film scopes.
- If Ollama or the compatible index is unavailable, the response explicitly
  marks itself degraded and uses lexical retrieval. It never labels lexical
  output as semantic intelligence.
- Narrative proximity remains candidate evidence. It does not create an
  `Assertion`, `Claim`, or `FilmRelationship`.
- There is no generated synthesis in v1. That may be added only through an
  interpretation-labelled adapter that cites these evidence records.

## Local verification

The initial product check compares *Her* and *Blade Runner 2049* with:

> How does each film make an artificial companion expose human loneliness?

The warm local hybrid request returned five paired evidence lenses in about
1.04 seconds on 2026-09-14. This is a development measurement, not a production
SLO. The first cold request may include local model-loading time.

Automated gates cover pure comparison policies, canonical research search,
the Next.js production build, and a real two-film PostgreSQL/API contract in
the isolated `cinegraph_test` database.

## Next acceptance gate

This workbench is ready for a small human evaluation, not corpus expansion.
Use 20 declared film pairs and writer questions. For every returned lens,
record whether the passages are relevant, misleading, duplicated, or missing.
Generated comparison prose must not be added until this evidence board is
useful on at least 70% of the reviewed tasks and has no unsupported factual
claims.
