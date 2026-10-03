# CineGraph

CineGraph is a source-linked film research desk for writers. Ask a writing question, compare two films' attributable passages, choose useful evidence, and save your own interpretation and creative move. Similarity is a research lead, not a film fact. The English collection is first; the entity and provenance model can admit later language editions without mixing them into English results.

## Current local milestone

- The current local database has 1,226 film profiles; the English writer collection has 1,000 films with 48,892 retained passages and 24,194 indexed chunks. These are coverage counts, not independent accuracy or usefulness scores.
- The writer desk supports question-first discovery, film-first source browsing by story, production, response, interpretation and legacy, film-pair comparison, alternate source passages, abstention when a question cannot be substantiated, and writer-authored study notes. Unfinished drafts recover after refresh, and the always-visible My studies shelf keeps saved notes available even before another comparison. Notes stay in the browser unless exported; JSON archives can be restored.
- Wikidata metadata and typed relationships retain source assertions and the reviewed operational `Assertion` projection. Wikipedia narrative passages remain attributed source text, not promoted facts.
- The local hybrid-retrieval benchmark measured finding a labeled passage in a candidate set; it does **not** establish that every displayed passage answers a writer's question. The 20-task writer study is still a development diagnostic, not a passed product-usefulness gate. See [writer-study findings](docs/writer-study-v2-findings-2026-09-29.md).
- Critical-essay discovery has an attribution-and-rights model, but the current corpus has no published critical claims. Link-only essays are not copied or embedded.

The local database is intentionally excluded from Git. Regenerate it from the source instead of committing scraped/derived data.

## Quick start

```bash
docker compose up --build -d
```

Open `http://localhost:3000`. Compose starts PostgreSQL, a one-shot migration
job, the API, then the web app. It preserves database and raw-snapshot volumes;
it does **not** scrape or ingest anything on startup. The API is at
`http://localhost:8000/api/v1`. Local ports bind to loopback by default. Set
`CINEGRAPH_BIND_ADDRESS` deliberately for access from another device; never
expose the default PostgreSQL credentials publicly.

For direct Conda development against the same local PostgreSQL container:

```bash
conda env create -f environment.yml
conda activate cine-graph
# Use the host-accessible URL in .env.example; keep the real .env out of Git.
cp .env.example .env
PYTHONPATH=backend python -m app.migrations
PYTHONPATH=backend uvicorn app.main:app --reload
```

The API checks the current Alembic revision at startup and never migrates it
implicitly. Do not point tests at this working database. The isolated
`cinegraph_test` stack and local browser test use:

```bash
backend/scripts/run_integration_tests.sh
cd frontend && npm test && npm run build
# With the isolated API running: CINEGRAPH_CHROME_PATH=/path/to/chrome npm run test:e2e
```

## Explicit data jobs

These jobs are for rebuilding or extending a local corpus, not for browsing
the app. Review [source policy](DATA_SOURCES.md) before any external access.

```bash
# Build the reproducible English 2000–2025 reference shelf (default: 1,000 films).
# This is not an IMDb-derived list or a rating rank.
PYTHONPATH=backend python -m app.services.english_reference_shelf --limit 1000
# Import the complete attributed CMU archive; it checkpoints every 250 records.
PYTHONPATH=backend python -m app.services.cmu_movie_summaries --archive /path/to/MovieSummaries.tar.gz
# Reconcile its records and fetch their canonical CC0 metadata. Omit --limit for the full run.
PYTHONPATH=backend python -m app.services.cmu_wikidata_reconcile --page-size 100
# Backfill the additive canonical-entity and evidence layer from an existing catalog.
PYTHONPATH=backend python -m app.services.backfill_evidence_core
# Project current retained raw statements into the operational Assertion graph.
# Generated JSON/HTML coverage reports remain local under data/.
PYTHONPATH=backend python -m app.services.source_assertion_projection \
  --collection english-1000-retained-narrative-v1 \
  --report-dir data/evaluation/source-assertion-projection-v1
# Extract a retained English Wikipedia revision into attributable passages.
# This command does not fetch pages: run the revision-snapshot adapter first.
PYTHONPATH=backend python -m app.services.wikipedia_research Q163872 --curate-pilot --quality
```

Ingestion is intentionally explicit so source-access decisions and local data
changes are visible; ordinary API startup never fetches source pages.

An older local catalog is stamped at the documented Alembic legacy baseline
and upgraded in place, never reset. The evidence-core backfill is separate
and idempotent so operators can inspect it before read projections change.

Raw-statement projection is also explicit and idempotent. It reads no network
source, selects only the latest retained successful snapshot for each Wikidata
object, retracts projections from superseded snapshots, and never promotes an
unclassified work target to a reviewed film relationship.

The API starts at `http://localhost:8000`; catalog health is available at `/api/v1/health`.
`/api/v1/corpus/quality` reports source records, narrative documents, matches,
release events, and explicit work relationships. The CMU import's `--limit`
option is only for validation. Both CMU ingestion and CMU-to-Wikidata
reconciliation commit bounded source pages, so an interrupted run can be
repeated without duplicating source records.

## Narrative research contract

See [docs/narrative-research-layer.md](docs/narrative-research-layer.md). A
Wikipedia-derived card is never silently treated as a fact: it is labelled as a
source fact, narrative extraction, derived relation, attributed interpretation,
or semantic candidate. Each card retains its source snapshot, revision, section
path and passage-level evidence. Embeddings index only eligible licensed
passages; similarity can suggest a route but cannot publish a claim. See
[docs/hybrid-retrieval-benchmark-v1.md](docs/hybrid-retrieval-benchmark-v1.md)
for the versioned gate, held-out results, latency, and known coverage debt.
The first product-facing consumer of this layer is documented in
[docs/story-comparison-v1.md](docs/story-comparison-v1.md).

## Critical essay contract

See [docs/critical-essay-sources-v1.md](docs/critical-essay-sources-v1.md).
Critical writing is a distinct meaning layer. A Medium or other link-only work
stores author, link and attributed interpretation—not copied prose or
embeddings. Reusable full text must have a work-level compatible licence and an
immutable source snapshot; every public critical claim is separately reviewed.

## Source policy

See [DATA_SOURCES.md](DATA_SOURCES.md). Any future HTML collector must pass a terms review and a fail-closed `robots.txt` check before it can request content. The current Wikidata adapter uses its documented query API, an identifying user agent, sequential pacing, and rate-limit/denial handling.
