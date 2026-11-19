# Product recovery execution ledger

## Phase 1: metadata source shapes and recovery contract

- Accepted the 24-hour recovery plan as the implementation contract.
- Recognize the local IMDb year-only release assertion and IMDb/TMDb integer
  minute runtime shape in the read projection, without changing stored facts.
- Preserve year precision (no invented day), source provenance, and conflicts.
- Focused verification: 21 passed, one database test deselected, using the
  explicit cine-graph Conda interpreter. Includes snapshot integrity policies
  and new root-map configuration tests currently being implemented.
- Prior read-only measurement of the revised projection: 510/1,000 unambiguous
  runtimes in the local source-inclusive catalog, not 1,000 approved values.
  This is an audit measurement, not a fresh serving deployment measurement.
- Source-path wiring remains in progress and is not part of the metadata commit.
- No model has been replaced, no source approvals have been bulk granted,
  and no working-corpus records have been changed by this phase.

Next: finish mapped-source verification with runtime and isolated-DB checks,
then prepare reconciled source manifests and the pinned >=4B model profile.

## Phase 2: application namespace for retained sources

- Added explicit validated snapshot root mappings to application configuration.
- All default snapshot verification callers now use this namespace, including
  rights and publication checks; explicit audit mappings remain independent.
- Missing/mismatched bytes still fail. Stored descriptors are unchanged.
- Added a real subprocess environment check, without mock frameworks, proving
  that a mapped capture verifies and an out-of-scope source stays unmapped.
- Deployment configuration is documented in snapshot-root-mapping.md; this
  commit does not silently mount a host directory or change the running API.

## Phase 3: immutable build-input inventory

- Added a repeatable-read, read-only corpus manifest builder with source and
  passage hash checks, decision versions, explicit exclusions, and stable
  canonical payload digest. It cannot approve or activate anything.
- Real local run inside the API namespace: 1,000 film rows, two build-eligible
  films; payload SHA-256
  `1597ae269aa11be743c0ce6376eb57087047cceee5186548e2dbc37a931d8ee8`.
  Full report remains ignored/local at
  `data/reports/corpus-build-input-2026-11-20-v2.json`.
- Host namespace run returned zero because Docker snapshots were inaccessible;
  retained separately as v1, not misreported as data loss.
- Pure admission and manifest stability checks: two passed. Existing full
  catalog was read, not changed. Target CSV identity reconciliation and model
  index construction remain separate unfinished gates.
