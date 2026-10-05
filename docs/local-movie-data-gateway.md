# Local movie data gateway: operator runbook

This pipeline is an offline corpus job, not an API request handler. It accepts
Hollywood or Indian film lists and keeps the IMDb dumps, TMDb credential, raw
payloads, database, reports, and model derivatives outside Git. New lists use
the same stages; language and country are properties of each film, not of the
pipeline. Run it against a local PostgreSQL corpus only.

## Inputs and identity gate

Place the IMDb title TSVs under `imdb_data/`, `name.basics.tsv` at the project
root, and the TMDb developer bearer token in `tmdb_api.env`. A JSONL manifest
has one film per line:

```json
{"title":"A Film","year":2020,"imdb_id":"tt1234567","wikidata_id":"Q1234567","language_code":"te","selection_source_url":"https://www.wikidata.org/wiki/Q1234567"}
```

The title and year are leads. An exact IMDb ID is preferred; without one, the
gateway admits a unique exact title/year or a near-title with the specified
actor's IMDb principal credit. Ambiguous records remain unresolved. A QID must
not be attached to an existing different IMDb film without explicit,
source-backed reconciliation. If Wikidata assigns the same IMDb ID to multiple
QIDs, selection excludes it until an operator records the correct QID with a
reason and source URL. The selection language bucket is not a definitive
single original-language claim: multilingual P364 values are reconciled after
Wikidata projection.

## Reproducible stages

Run from the project root after the schema migration. The Docker `ingest`
service is an optional equivalent for the IMDb and TMDb steps; it mounts the
source files read-only. These examples assume `PYTHONPATH=backend` and an
appropriate `DATABASE_URL` in the local environment.

1. Build the sparse IMDb index once: `python -m app.services.imdb_dataset
   --data-dir imdb_data --index-dir data/imdb_index`.
   Its file hashes allow cheap, deterministic replay without importing the
   entire dump into PostgreSQL.
2. For a new list, run `python -m app.services.movie_data_gateway --data-dir
   imdb_data --index-dir data/imdb_index --manifest data/manifests/my-list.jsonl
   --create --collection my-research-list --report data/reports/my-list-imdb.json`.
   Inspect every unresolved or error row before continuing. Replays reuse
   identical snapshots and source assertions.
3. If QIDs are missing, run `python -m
   app.services.wikidata_imdb_resolver --data-dir imdb_data --index-dir
   data/imdb_index --manifest data/manifests/my-list.jsonl --output
   data/manifests/my-list-with-qids.jsonl --report
   data/reports/my-qid-resolution.json`. This uses exact IMDb P345, leaves
   missing/multiple QIDs for review, and never merges by title alone. If QIDs
   are present, snapshot their Wikidata entities with `python -m
   app.services.wikidata_raw --manifest data/manifests/my-list.jsonl`, then
   project the allow-listed facts with `python -m
   app.services.source_assertion_projection --manifest
   data/manifests/my-list.jsonl`. Source statements remain
   separate from reviewed operational assertions. Run `python -m
   app.services.review_wikidata_imdb_ids --data-dir imdb_data --index-dir
   data/imdb_index --manifest data/manifests/my-list.jsonl --report
   data/reports/my-identity-audit.json` to detect extra P345 values. Review
   before `--apply`: it downgrades only extra IDs absent from the local IMDb
   dump, retaining the raw statements; an extra existing ID needs manual
   disambiguation.
   If the QIDs were added after an IMDb-only film already existed, first run
   `app.services.reconcile_manifest_identities --prepare-qids` in dry-run and
   apply mode so the QID subjects exist for projection. After projection, run
   the same operator without `--prepare-qids` in dry-run and apply mode to
   unify only source-proven duplicate film entities.
4. Reconcile source-declared languages with `python -m
   app.services.reconcile_manifest_languages --manifest
   data/manifests/my-list.jsonl --report data/reports/my-language-audit.json`.
   Only use `--apply` after reviewing the dry-run. Published profiles require
   an explicit `--approved-updates` JSONL with QID, expected code, and reason.
5. Derive English Wikipedia jobs only from retained Wikidata enwiki sitelinks:
   `python -m app.services.wikipedia_sitelink_manifest --selection
   data/manifests/my-list.jsonl --output-dir data/manifests/my-wikipedia`.
   Then run `python -m app.services.wikipedia_narrative_jobs --manifest-dir
   data/manifests/my-wikipedia --report data/reports/my-wikipedia.json`.
   Completed chunks are checkpointed. A missing sitelink stays a reported gap;
   no guessed page is silently joined.
6. Add TMDb with the same manifest and `--tmdb-key-file tmdb_api.env` on the
   movie gateway. Each match must be unique by IMDb cross-ID and the detail
   response must confirm that ID. Calls are serial and paced. A second run
   skips verified local TMDb snapshots; `--refresh-tmdb` is explicit. The
   overview is retained as a short, attributed narrative passage, not treated
   as a full plot or a canonical fact.
7. Run `python -m app.services.audit_movie_collection --collection
   my-research-list --report data/reports/my-quality.json`. Review title and
   identity mismatches, missing passages, missing characters, and field-level
   source conflicts before allowing the collection into writer-facing search.

For an existing IMDb-only entity and a separately created QID entity, use
`app.services.reconcile_manifest_identities` in dry-run mode first. It requires
reviewed Wikidata film type and IMDb ID, plus the IMDb source's matching ID;
only then may `--apply` move references while retaining the old entity as
merged. Never run it against an arbitrary title-only pair.

## Quality and rights boundary

The first Indian research cohort is 500 cross-language candidates selected
from retained Wikidata queries and local IMDb audience signals. It is not an
authoritative “greatest 500” ranking. The quality audit counts source-backed
coverage, not factual correctness: missing Wikipedia plot/production/reception
sections and conflicts need human review. Raw source snapshots, source
assertions, and current operational assertions must remain distinguishable.

The supplied IMDb datasets and TMDb developer key are used for local,
non-commercial research. Their data and the key are not Git artifacts.
Shipping this corpus in a commercial product requires a separate rights
review/license; Wikipedia prose also carries attribution and share-alike
obligations. No automated collector may bypass source terms, robots controls,
or a rate-limit response.

At 100,000 films, index and snapshot storage grow locally and ingestion can
be sharded by manifests without changing source or fact schemas. Do not add a
new database or background cluster merely for the pilot: keep ingestion
checkpointed and offline, and benchmark read latency separately from source
acquisition. A failed chunk is a retry target; it is not a reason to recrawl
all previously verified films.
