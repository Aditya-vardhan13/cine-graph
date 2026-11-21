# Corpus build input inventory

`backend/scripts/prepare_corpus_build_manifest.py` reads an included-film
collection under a repeatable-read, read-only PostgreSQL transaction and
creates a new local JSON file. It refuses overwrite and empty selections.
Raw narrative text is not copied into the inventory.

Every film row binds entity ID, title, QID and current extraction to snapshot
ID/hash/revision, licence, attribution, latest semantic-use decision version,
verified file integrity, and passage IDs/hashes. The report has a canonical
payload hash. A snapshot can be build-eligible only when permission,
retained-byte integrity, nonempty current passages and passage hashes pass.
One eligible source makes the film eligible for that source, not all its text.
Downstream builders must still select the eligible source rows, not import
every source attached to an eligible film.

Version 2 also records and requires `fetch_status=success`, matching the
writer-index builder's capture requirement. Older version 1 inventories did
not check this field and must not be treated as equivalent readiness evidence.

This is **not** approval, full target-CSV reconciliation, an index, or a
film-level accuracy guarantee. Identity review is explicitly marked unperformed.
Missing profiles and source gaps need separate target reconciliation.
No source or model is activated by running the command.

Example (inside the namespace with access to both mounted snapshot roots):

```sh
PYTHONPATH=backend python backend/scripts/prepare_corpus_build_manifest.py \
  --output data/reports/corpus-build-input-new.json \
  --path-map /Users/vkammela/Downloads/aarambham/data=/app/data \
  --path-map /var/lib/cinegraph/raw-snapshots=/var/lib/cinegraph/raw-snapshots
```

The example mappings are local deployment details, not portable defaults.
The standalone host cannot read a Docker volume just because a descriptor
names its container path. Keep unsuccessful host reports with their namespace
limitations; don't claim those captures were deleted.
