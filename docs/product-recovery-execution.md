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

## Pilot review: first source admission

- Read exact current leads and snapshot descriptors for nine pilot titles,
  resolving WALL-E's stored spelling separately as WALL·E, Q104905.
- Reviewed Wikipedia's copyright policy and CC BY-SA 4.0 terms for the intended
  attributed local text experiment. Linked sources/images are not inherited
  permissions, and this is not a paid-release legal determination.
- Her (2013), Q788822, snapshot
  335aa8a4-9b6f-4735-9249-b719b6a15c17, revision 1382870252:
  retained lead identifies the director and central relationship consistently.
  Snapshot and passage hashes were bound by the current build manifest.
- Recorded one explicit snapshot-specific semantic-use approval through the
  existing local operator API (HTTP 200, decision version 1). Notes retain the
  exact hash, source basis, attribution/derivative obligations and limitations.
  This is a persistent decision, not a bulk approval or canonical fact write.
- Important: local intent in the notes is documentary, not an additional
  machine-enforced use-case scope. Public deployment still requires the
  separate release gates. No film was published or indexed by this decision.
- Remaining pilot sources require their own recorded review before admission;
  this does not establish source content correctness or answer usefulness.

- WALL·E (2008), Q104905: snapshot a3ffc9dd-5348-4d4f-b264-e6c68802bb30,
  revision 1380240647, SHA-256
  6ebcb396a361eb890b0863834471efb5bc6f6214067f36e1bd4c93ea1864adba:
  retained lead identifies Pixar/Stanton and the WALL-E/EVE relationship.
  Recorded its own explicit approval via local API, HTTP 200, version 1.

## Resource cleanup for the >=4B experiment

- Free disk fell below the 6 GiB reserve before the two-film diagnostic.
- Removed only the retired BGE-M3 checkpoint blob under the project-local
  rag-v2/encoders/weights cache: 2,271,145,830 bytes, SHA-256
  b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38.
  Hash matched its cache identity; it was ignored, not a symlink, with no
  open handle or running BGE evaluation observed. New model selection excludes
  this sub-4B model. Kept old scores, vectors, annotations and raw captures.
- Not recoverable from Git or Trash; old BGE experiments require re-acquiring
  this exact pinned checkpoint to replay inference. Cached model metadata may
  now point to an absent blob; no ordinary tests auto-download it.

## Current-source 4B diagnostic started

- Exported 79 current, approved and hash-verified passages for Her/WALL·E into
  an ignored local packet. Corpus fingerprint:
  924b797a1e96e716243c7990cb16526a8e615337471fd9f985069666509e341d.
- Reused the existing 128-word overlapping-window diagnostic runner, not a
  new production chunker: 158 source windows and one known development query.
- Added immutable output protection, per-batch 6 GiB reserve checks and
  digest verification through the adapter on every uncached inference batch.
- Three existing dense-trial policy tests passed. No quality score is implied.
- Live job handle for this turn: unified exec 13255. Resumable artifacts:
  data/evaluation/recovery-qwen4b-cache and
  data/evaluation/recovery-her-walle-qwen4b-v1.json (final report when complete).

### Completed diagnostic, not a release score

- Job 13255 exited successfully: 158 document windows and one query; measured
  embedding batch time total 132.93 seconds. This excludes some orchestration
  overhead and is not representative 1,000-film throughput or user latency.
- Her top lead is its opening plot passage, directly establishing Theodore's
  loneliness and connection to Samantha. Second is the plot's separation/
  acceptance passage, relevant to how the relationship changes. Third is a
  production passage, useful background but not the characters' choice itself.
- WALL·E top lead is an attributed thematic discussion about habit and
  relationships, followed by an animation discussion and then the plot's
  arrival of EVE/care for EVE. This is pertinent context but direct dramatic
  action should not be displaced by thematic exposition in the final answer.
- Several windows begin or end mid-sentence. Parent-context expansion and
  sentence/paragraph-aligned chunking need evaluation before production.
- Result demonstrates access to useful current evidence outside the old
  plot-only route, not superiority of 4B over another model. It is one known
  development query, without independent labels, reranking or synthesis.
- Next: improve evidence packing, expand to the reviewed ten-film pilot and
  frozen questions, then compare model arms on the same complete corpus.

### Aligned-window ablation: not a retrieval win

- Added opt-in aligned400 policy with independent cache representation.
  Exact offsets and all source characters are preserved, oversized heuristic
  sentences remain whole and flagged; regex boundaries are not linguistic gold.
  Default fixed-window history remains reproducible. Four policy tests passed.
- On the same 79 passages and question the aligned run produced 79 windows;
  embedding batches totalled 102.99 seconds. Fewer/larger windows and cache/load
  effects differ, so this is not a model speed comparison.
- Her's opening plot remains first; production and introductory context displace
  the separation plot from the top three. WALL·E's animation/intent/design
  passages occupy the top three rather than the requested character choices.
- Therefore sentence-boundary preservation helped source readability but
  **did not establish better question coverage**. Do not promote this candidate
  to serving on the basis of cleaner text or fewer windows. Next evaluate
  query-facet selection, lexical/dense fusion and parent-context diversity
  against full-source support, before claiming success.
- Result: data/evaluation/recovery-her-walle-qwen4b-aligned-v1.json; sources
  and question unchanged, no live retrieval/index modification.

### Explicit evidence-facet packing diagnostic

- Added a pure bounded packing policy and an offline retained-ranking adapter.
  Only an explicit operator/evaluation request reserves a narrative lead;
  there is no new automatic keyword intent classifier or hard plot-only filter.
- Preserves the original dense rank, broad context, source identity, and an
  explicit support_validated=false label. Deduplicates repeated parent leads,
  fails on cross-film/missing parents, and reports absent facets.
- Two policy tests passed. On the aligned Her/WALL·E development result,
  selected ranks are Her 1–5 and WALL·E 1,2,3,4,8.
- Manually inspected the reserved WALL·E passage: it describes intervention
  at diagnostics, conflict with EVE, the plant retrieval and reconciliation.
  Those actions are relevant to the relationship-change facet, but do not
  alone establish isolation or validate a generated interpretation.
- This is improved visibility of a known relevant source, not a new dense
  recall/model score, a trained relevance label, or a serving change. The
  operator-provided facet is a limitation; automatic question interpretation,
  wider query classes and held-out evaluation are still required.
- Local result: data/evaluation/recovery-her-walle-facet-packing-v1.json.

## Fixed-evidence local 4B generation diagnostic: failed

- Started project-local Ollama 11435 from existing cached models (cloud off;
  server handle 89269), after unloading the embedding runner. No downloads.
- Added an explicit offline draft runner using existing grounded-answer schema
  and citation validator, pinned digest, fixed original evidence, bounded
  context/output, temperature zero, seed 42 and think=false.
- Generated with qwen3:4b, exact digest
  359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7.
  Request handle 94504 completed. Prompt 2,353 tokens, output 745 tokens,
  61.80 seconds including cold overhead; 16,384 configured context.
- Structural validation failed: first reading ended mid-sentence. Manual
  source inspection also found material attribution reversals: the blind
  date's insult was attributed to Samantha; EVE's suspicion about the missing
  plant was reversed into WALL-E suspecting EVE. Comparison support cites only
  Her, not both films. Some quoted strings exist but do not support the claim.
- **Do not enable this draft in the site.** Proper source references and JSON
  do not rescue unsupported analysis. Nine existing grounded-trial policy
  checks passed, but this real model output failed usefulness/grounding.
- Local artifact: data/evaluation/recovery-her-walle-draft4b-v1.json.
- Free disk crossed below 6 GiB during generation; no further inference should
  be queued until remeasured. No 8B comparison was attempted. Before next
  inference, measure memory, choose a token-counted smaller context and use
  source observations/citation-first construction rather than merely longer
  output or another unmeasured model sweep.
