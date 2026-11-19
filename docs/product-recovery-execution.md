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
