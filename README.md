# CineGraph

CineGraph begins as a public-data cinema intelligence platform. Phase A ingests English-language film metadata from a permitted structured source and retains provenance for every imported entity and field. It excludes scripts, subtitles, posters, and unlicensed article text; its one narrative layer is the separately attributed CC BY-SA CMU Movie Summary Corpus.

## Current milestone

- 24,776 English-language CMU plot records are available as an attributed, historical narrative-reference layer
- Canonical facts, credits, release events, and explicit work links are fetched only from Wikidata's CC0 structured data
- CMU records reconcile only through an exact CMU Freebase ID → Wikidata P646 match; title matching is deliberately excluded
- Source provenance, language-edition configuration, API catalog endpoints, and source-access controls are implemented

The local database is intentionally excluded from Git. Regenerate it from the source instead of committing scraped/derived data.

## Development setup

```bash
conda env create -f environment.yml
conda activate cine-graph
# Build the reproducible English 2000–2025 reference shelf (default: 1,000 films).
# This is not an IMDb-derived list or a rating rank.
PYTHONPATH=backend python -m app.services.english_reference_shelf --limit 1000
# Import the complete attributed CMU archive; it checkpoints every 250 records.
PYTHONPATH=backend python -m app.services.cmu_movie_summaries --archive /path/to/MovieSummaries.tar.gz
# Reconcile its records and fetch their canonical CC0 metadata. Omit --limit for the full run.
PYTHONPATH=backend python -m app.services.cmu_wikidata_reconcile --page-size 100
# Backfill the additive canonical-entity and evidence layer from an existing catalog.
PYTHONPATH=backend python -m app.services.backfill_evidence_core
PYTHONPATH=backend uvicorn app.main:app --reload
```

To run the full Explorer locally, use Docker Compose:

```bash
docker compose up --build -d
docker compose exec api python -m app.services.wikidata --limit 1000
```

Open `http://localhost:3000`. The frontend expects the API at
`http://localhost:8000/api/v1` by default.

The import is intentionally explicit: it makes the source-access decision and
the resulting local dataset visible instead of silently downloading data on
application startup. It fetches and commits 100-film source pages sequentially,
so an interrupted run can safely be repeated.

Database schema changes are managed by Alembic. The API upgrades a new database
at startup; an older local catalog is stamped at the documented legacy baseline
and upgraded in place, never reset. The evidence-core backfill is a separate,
idempotent command so operators can observe it before any API reads switch to
the new projections.

Run checks:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

The API starts at `http://localhost:8000`; catalog health is available at `/api/v1/health`.
`/api/v1/corpus/quality` reports source records, narrative documents, matches,
release events, and explicit work relationships. The CMU import's `--limit`
option is only for validation. Both CMU ingestion and CMU-to-Wikidata
reconciliation commit bounded source pages, so an interrupted run can be
repeated without duplicating source records.

## Source policy

See [DATA_SOURCES.md](DATA_SOURCES.md). Any future HTML collector must pass a terms review and a fail-closed `robots.txt` check before it can request content. The current Wikidata adapter uses its documented query API, an identifying user agent, sequential pacing, and rate-limit/denial handling.
