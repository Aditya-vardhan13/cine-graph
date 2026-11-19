# Retained source paths across host and container

Snapshot URIs are immutable. When the runtime mounts the same captured bytes at
a different location, set `SNAPSHOT_ROOT_MAPPINGS` to JSON pairs of absolute
persisted and mounted roots. Example for this project's historical host captures:

```json
[
  ["/Users/vkammela/Downloads/aarambham/data", "/app/data"],
  ["/var/lib/cinegraph/raw-snapshots", "/var/lib/cinegraph/raw-snapshots"]
]
```

This example is a machine-specific deployment configuration, not a new default.
Set it in the API/worker process environment (or a local Compose override).
No copies, URI updates, rights approvals or canonical fact changes are needed.
The target must be an actual read-only mount of the captured bytes.

When configured, sources outside every mapped root fail as unmapped; include
identity mappings for other permitted roots. An empty list retains native-path
behavior. Relative roots, filesystem root, and duplicate source-root strings
are rejected at startup. Path traversal, sibling-prefix and target symlink
escapes fail containment. Every successful lookup still checks the exact
snapshot SHA-256 and byte size. Explicit audit CLI mappings override the
application configuration, so an audit can retain its own namespace.

Configuration does not establish rights or identity, nor make a snapshot indexed.
Callers of `verify_snapshot_file`, including rights and publication checks,
now use configured mappings unless explicitly passed an audit mapping tuple.
Run `backend/tests/test_snapshot_mapping_config.py` for the real subprocess
environment contract, and `test_snapshot_integrity.py` for file/persistence
checks against the isolated test DB.
