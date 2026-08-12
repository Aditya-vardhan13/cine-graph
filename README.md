# CineGraph

CineGraph begins as a public-data cinema intelligence platform. Phase A ingests English-language film metadata from a permitted structured source and retains provenance for every imported entity and field. It intentionally does **not** ingest copyrighted scripts, subtitles, plots, posters, or article text.

## Current milestone

- 1,319 English-language films imported locally from Wikidata
- 15,056 people and 25,191 film credits
- 207 genres
- Source provenance, language-edition configuration, API catalog endpoints, and source-access controls are implemented

The local database is intentionally excluded from Git. Regenerate it from the source instead of committing scraped/derived data.

## Development setup

```bash
conda env create -f environment.yml
conda activate cine-graph
PYTHONPATH=backend python -m app.services.wikidata --limit 1000
PYTHONPATH=backend uvicorn app.main:app --reload
```

To run the full Explorer locally, use Docker Compose:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The frontend expects the API at
`http://localhost:8000/api/v1` by default.

Run checks:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

The API starts at `http://localhost:8000`; catalog health is available at `/api/v1/health`.

## Source policy

See [DATA_SOURCES.md](DATA_SOURCES.md). Any future HTML collector must pass a terms review and a fail-closed `robots.txt` check before it can request content. The current Wikidata adapter uses its documented query API, an identifying user agent, sequential pacing, and rate-limit/denial handling.
