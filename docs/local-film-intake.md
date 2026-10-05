# Local film intake: operator flow

This is a local research workflow, not public self-service ingestion. The
browser searches the operator-supplied IMDb index; selecting a result fixes an
exact `tt…` film ID. It also accepts HTTPS `imdb.com/title/tt…/` URLs. It does
not fetch arbitrary URLs or infer identity from a fuzzy title. Up to 20 films
can be submitted at once. Duplicate submissions reuse their existing job.

## Start the local pilot

1. Keep the IMDb TSVs in `imdb_data/`, `name.basics.tsv` in the project root,
   and the TMDb developer token in `tmdb_api.env`. These and `data/` stay local.
2. Build the local index once with `docker compose --profile tools run --rm
   ingest python -m app.services.imdb_dataset`. If an index already exists,
   add popularity ranking for suggestions with the same command plus
   `--ratings-only`.
3. Generate a long random operator key (for example, `openssl rand -hex 32`)
   and place `CINEGRAPH_ADMIN_TOKEN=<key>` in a local `.env` file. Never commit
   or share it. The admin API refuses all requests if the key is absent or
   shorter than 24 characters.
4. Run `docker compose up --build -d`. Open
   `http://localhost:3000/admin/intake`, enter the operator key, then search,
   select, and submit films. The key stays only in the current browser tab.

The separate `intake_worker` service claims queued rows from PostgreSQL and
processes one film at a time. It first resolves Wikidata by exact IMDb P345,
verifies P31 film identity, and projects source assertions so an existing
Wikidata film profile cannot be duplicated. It then reconciles only
source-proven duplicate identities, reuses or acquires IMDb/TMDb snapshots,
and ingests the Wikidata-linked English Wikipedia revision and passages.
Each stage is visible in the UI. Rate limits and source denials remain in the
existing adapters; the worker does not scrape IMDb or bypass robots controls.
Re-running a failed job reuses retained snapshots where the adapters support
it. A crashed `running` job is eligible for reclaim after 30 minutes.

`ready` means the identity checks, TMDb cross-ID, English Wikipedia page, and
full plot passage were found. `ready_with_gaps` means source identity was
proved but one or more enrichment sources/fields (possibly the full plot) were
unavailable. `needs_review` means a source identity could not safely be
established or an existing conflicting profile requires an operator decision.
These statuses do not certify factual correctness, complete casting, artistic
quality, or commercial usage rights.

The operator key is a deliberately local pilot gate, **not email login**.
Before exposing this route on a public host, integrate verified Google OAuth
and allow only `adityavk1310@gmail.com`; do not trust a client-supplied email
string. The worker and local source corpus also remain private until the
rights review in [DATA_SOURCES.md](../DATA_SOURCES.md) is complete.
