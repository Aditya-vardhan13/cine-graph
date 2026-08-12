# CineGraph

CineGraph begins as a public-data cinema intelligence platform. Phase A ingests English-language film metadata from a permitted structured source and retains provenance for every imported entity and field. It intentionally does **not** ingest copyrighted scripts, subtitles, plots, posters, or article text.

## Current milestone

- 1,319 English-language films imported locally from Wikidata
- 15,056 people and 25,191 film credits
- 207 genres
- Source provenance, language-edition configuration, API catalog endpoints, and source-access controls are implemented
- An explicit CMU Movie Summary Corpus importer and corpus-quality endpoint are available for the next, attributed narrative-reference layer

The local database is intentionally excluded from Git. Regenerate it from the source instead of committing scraped/derived data.

## Development setup

```bash
conda env create -f environment.yml
conda activate cine-graph
PYTHONPATH=backend python -m app.services.wikidata --limit 1000
# Explicitly import a small CMU validation sample from a downloaded archive.
PYTHONPATH=backend python -m app.services.cmu_movie_summaries --archive /path/to/MovieSummaries.tar.gz --limit 3
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

Run checks:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

The API starts at `http://localhost:8000`; catalog health is available at `/api/v1/health`.
`/api/v1/corpus/quality` reports source records, narrative documents, matches,
release events, and explicit work relationships. The CMU import's `--limit`
option is only for validation, not a production corpus-selection strategy.

## Source policy

See [DATA_SOURCES.md](DATA_SOURCES.md). Any future HTML collector must pass a terms review and a fail-closed `robots.txt` check before it can request content. The current Wikidata adapter uses its documented query API, an identifying user agent, sequential pacing, and rate-limit/denial handling.
