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

## Phase 4: pinned 4B adapter contract, no new weights

- Local Ollama 11434 already has Qwen3-Embedding 4B Q4_K_M, about 2.5 GB.
  Exact digest: df5bd2e3c74cd8d069d21dc038f1b359fcdc9458fce1c99bd43c9eb1518ff907.
  The dedicated story server on 11435 did not return a model inventory.
- Added an explicit local-only candidate check restricted to >=4B candidates:
  pins registry digest before/after inference and checks vector shape,
  finiteness, nonzero norms and query/document adapter compatibility.
- Observed 1,024-dimensional vectors with norms near one; three original
  diagnostic sentences took 4.95 seconds including any load overhead;
  a query took 0.41 seconds. Not full-corpus throughput or quality evidence.
- One pure vector-contract test passed. Result remains local at
  data/reports/embedding-candidate-qwen4b-contract-v1.json.
- No download, index build, source approval or serving switch. Long inputs,
  retrieval relevance, 8B comparison, production profile activation and
  generation remain unverified. Disk fell from about 8.6 to 6.6 GiB during
  the check; cause not established, so heavier jobs must recheck reserve.

## Phase 5: target-to-build reconciliation

- Reused the frozen CSV and historical candidate mapping instead of inventing
  fresh title joins. Input fingerprints, row order/year and current manifest
  hash must agree; malformed rank sets or source drift fail closed.
- Supplied CSV has 1,001 data rows. The established target is its first 1,000;
  the extra row is accounted for, not silently included in coverage.
- Result: 968 target rows have one historical-QID candidate in the current
  collection; 32 are unresolved or outside it. Two have an eligible candidate.
  Zero identity approvals are implied or written.
- Report stays local: data/reports/recovery-target-reconciliation-v1.json,
  canonical payload SHA-256
  d905dabb39887c558e895ba83459dbeee293ad098f5bd596a216f5f2cfc6fa17.
- Two policy tests passed for stable mapping, extra-row accounting, CSV drift
  and manifest tampering. This is a queue for review; it does not establish
  independent identity correctness, all required sources, or usable retrieval.
