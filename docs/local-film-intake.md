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
3. The local pilot currently uses an email-string gate, not a service token or
   verified login. Compose configures the expected value as
   `CINEGRAPH_ADMIN_EMAIL` (default `adityavk1310@gmail.com`). Do not expose the
   service beyond loopback; anyone who can reach the local web server can enter
   that address. Production authentication is not implemented.
4. Run `docker compose up --build -d`. This starts the API, web app, database,
   migrations and `intake_worker`. Open `http://localhost:3000/admin/intake`,
   enter the configured email, then search, select and submit films. The worker
   processes queued jobs serially; if you start only selected services, include
   `intake_worker` or submitted jobs will remain queued.

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
Completed jobs offer an operator preview of reviewed metadata, narrative
section counts, short source passages and attribution links. Intake does not
publish a film into the writer comparison index; that requires a separate
quality and indexing gate. Preview and coverage checks use the newest captured
revision of each source object; earlier snapshots remain stored for provenance.

Current terminal states are `captured` and `captured_with_gaps`: capture and
extraction finished, with the latter naming missing sources/fields. Older
persisted `ready` and `ready_with_gaps` states are displayed as legacy capture
statuses. `needs_review` means identity or an existing conflicting profile
needs an operator decision; `failed` means capture failed. None of these states
means rights approval, indexing, factual correctness, complete casting,
artistic quality or commercial clearance. Rights review, eligible chunking and
embedding are separate explicit stages.

The email field is a local operator selector, not verified login. Anyone with
access to the local web server could enter this email; keep this pilot bound to
loopback. The web server passes its private service key to the API and never
returns that key to the browser. Local admin routes are disabled unless
`CINEGRAPH_LOCAL_ADMIN_MODE=1` is explicitly configured.
The route also refuses requests if `CINEGRAPH_BIND_ADDRESS` is changed from
`127.0.0.1`; use verified sign-in before exposing the web service remotely.
Before exposing this route on a public host, integrate verified Google OAuth
and allow only `adityavk1310@gmail.com`; do not trust a client-supplied email
string. The worker and local source corpus also remain private until the
rights review in [DATA_SOURCES.md](../DATA_SOURCES.md) is complete.
