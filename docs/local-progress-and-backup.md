# Local progress and corpus backups

CineGraph uses one local PostgreSQL + pgvector database for the current pilot.
Film/person/assertion records, text-search indexes, and vector indexes fit this
model; a second graph or vector database would add operational and backup cost
before we have evidence that it is needed. Revisit the choice only when measured
query latency, index size, or write contention fails agreed targets.

## What is protected where

- GitHub protects application code, migrations, plans, and small fixtures.
- The local PostgreSQL volume contains structured corpus state and vectors.
- The `raw_snapshots` Docker volume and `data/raw-snapshots` contain source
  payloads. They remain local and are intentionally excluded from Git.
- The backup script creates a PostgreSQL custom-format dump, archives both
  snapshot locations, validates the archive listings, and records SHA-256
  checksums and the source Git revision.

## Create a backup

Start the local Compose database, then choose a backup directory outside the
repository. For example:

```sh
./backend/scripts/backup_local_corpus.sh /Users/vkammela/Downloads/cinegraph-backups
```

Each run creates a new `cinegraph-<UTC timestamp>` directory and refuses to
overwrite one. Keep the backup directory on a different physical device if the
goal is protection from disk failure; a sibling folder on the same disk only
protects against accidental repository deletion. Keep at least one recent
backup before schema migrations or corpus rebuilds, and make routine backups
after meaningful ingestion/review milestones.

## Verify and restore

Verify checksums before using a backup:

```sh
cd /path/to/cinegraph-YYYYMMDDTHHMMSSZ
shasum -a 256 -c SHA256SUMS
pg_restore --list cinegraph.dump
tar -tzf docker-raw-snapshots.tar.gz >/dev/null
```

Restore the database into a **new, empty** local database/volume first; do not
restore over the working corpus. For example, provision an isolated Compose
project with a fresh PostgreSQL volume, then run `pg_restore --no-owner --dbname
<new-database-url> cinegraph.dump`. Extract snapshot archives into their matching
mounts while the application is stopped. Validate snapshot checksums and a
read-only corpus audit before switching the app to the recovered volume. The
optional workspace archive is absent when `data/raw-snapshots` did not exist at
backup time.

The dump and snapshot archives may be large and contain licensed source text;
keep them private, local, and access-controlled. This workflow is a recovery
mechanism, not a data publication/export step.
