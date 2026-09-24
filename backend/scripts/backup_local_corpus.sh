#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname "$0")" && pwd -P)
repo_root=$(CDPATH= cd -- "$script_dir/../.." && pwd -P)

if [ "$#" -ne 1 ]; then
  printf '%s\n' "Usage: $0 /absolute/path/to/backups" >&2
  exit 2
fi

backup_parent=$1
case "$backup_parent" in
  /*) ;;
  *) printf '%s\n' "Backup destination must be an absolute path outside the repository." >&2; exit 2 ;;
esac

mkdir -p "$backup_parent"
backup_parent=$(CDPATH= cd -- "$backup_parent" && pwd -P)
case "$backup_parent" in
  /|"$repo_root"|"$repo_root"/*)
    printf '%s\n' "Choose a specific backup directory outside the repository." >&2
    exit 2
    ;;
esac

if ! docker compose exec -T db pg_isready -U postgres -d cinegraph >/dev/null; then
  printf '%s\n' "The local cinegraph database is not ready; start the Compose database first." >&2
  exit 1
fi

timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
stage_dir=$(mktemp -d "$backup_parent/.cinegraph-backup-${timestamp}.XXXXXX")
backup_dir="$backup_parent/cinegraph-$timestamp"

if [ -e "$backup_dir" ]; then
  printf '%s\n' "Refusing to overwrite existing backup: $backup_dir" >&2
  exit 1
fi

# Each source-snapshot transaction is committed independently. pg_dump takes
# one consistent database snapshot; source payload stores are immutable files.
docker compose exec -T db pg_dump -U postgres -Fc cinegraph > "$stage_dir/cinegraph.dump"
docker compose run --rm --no-deps -T -v "$stage_dir:/backup" api python -c \
  'import tarfile; archive=tarfile.open("/backup/docker-raw-snapshots.tar.gz", "w:gz"); archive.add("/var/lib/cinegraph/raw-snapshots", arcname="raw-snapshots"); archive.close()'

if [ -d "$repo_root/data/raw-snapshots" ]; then
  tar -czf "$stage_dir/workspace-raw-snapshots.tar.gz" -C "$repo_root" data/raw-snapshots
else
  : > "$stage_dir/workspace-raw-snapshots.absent"
fi

docker compose run --rm --no-deps -T -v "$stage_dir:/backup:ro" db pg_restore --list /backup/cinegraph.dump >/dev/null
tar -tzf "$stage_dir/docker-raw-snapshots.tar.gz" >/dev/null
if [ -f "$stage_dir/workspace-raw-snapshots.tar.gz" ]; then
  tar -tzf "$stage_dir/workspace-raw-snapshots.tar.gz" >/dev/null
fi

{
  printf 'format=1\n'
  printf 'created_utc=%s\n' "$timestamp"
  printf 'git_revision=%s\n' "$(git -C "$repo_root" rev-parse HEAD)"
  printf 'database=cinegraph.dump\n'
  printf 'docker_snapshot_store=docker-raw-snapshots.tar.gz\n'
  if [ -f "$stage_dir/workspace-raw-snapshots.tar.gz" ]; then
    printf 'workspace_snapshot_store=workspace-raw-snapshots.tar.gz\n'
  else
    printf 'workspace_snapshot_store=absent-at-backup-time\n'
  fi
} > "$stage_dir/manifest.txt"

(
  cd "$stage_dir"
  if [ -f workspace-raw-snapshots.tar.gz ]; then
    shasum -a 256 cinegraph.dump docker-raw-snapshots.tar.gz \
      workspace-raw-snapshots.tar.gz manifest.txt
  else
    shasum -a 256 cinegraph.dump docker-raw-snapshots.tar.gz manifest.txt
  fi
) > "$stage_dir/SHA256SUMS"

mv "$stage_dir" "$backup_dir"
printf 'Backup complete: %s\n' "$backup_dir"
