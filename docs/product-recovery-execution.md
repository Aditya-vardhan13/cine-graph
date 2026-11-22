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

## Ten-film diagnostic source admission

- Recorded eight additional individually reviewed current Wikipedia snapshots
  through the local operator API. Each decision note binds the exact snapshot,
  revision, SHA-256, film/edition, recognizable lead identity, source basis,
  attribution/change obligations and local-experiment limitations. This is
  not an approval rule for other catalog titles or future source revisions.
- Source decisions persisted (QID / exact snapshot / latest version):

| Film QID | Snapshot | Version |
| --- | --- | --- |
| Q2345 | fa096951-cff7-465e-a7d9-959ab2c428af | 1 |
| Q229633 | e835e7c7-09d3-4893-812b-a1c684dccf6a | 1 |
| Q23781155 | 2278450f-8125-4dcd-a7d3-94b48877db27 | 2 |
| Q167726 | 7a0579fa-169f-4b0a-9425-ffa95014985b | 1 |
| Q7117022 | ddad809a-afbc-45ce-80c1-091e52104a44 | 1 |
| Q189505 | eac2d9f9-5f25-4431-af30-4d0a99eeeb6d | 1 |
| Q47703 | a2c2124d-2482-40f7-b2eb-939ad26d1939 | 2 |
| Q172241 | e6890241-da9e-48bf-b733-b607faa40960 | 1 |

- Her and WALL·E were admitted in the previous checkpoints. Re-read the current
  source selection, latest decisions, purpose policy and retained-file hashes
  in the API namespace after these operations. All ten selected films have
  at least one eligible current source; this does not make other sources
  attached to those films eligible or establish all factual correctness.
- Endgame/Godfather already had a decision on these snapshots, so their new
  source-specific reviews are version 2 rather than version 1; no history
  was overwritten.
- Raw local response log: data/reports/recovery-pilot-source-decisions-v1.json.
  No facts or collection memberships changed. No full pilot index, serving
  switch, held-out evaluation, or quality certification is implied.
- Generator is now unloaded (local /api/ps returned no models), but free disk
  is about 5.4 GiB. New inference/download work remains capacity-gated.

## Fifty-question recovery design

- Added ten distinct pairs over the ten admitted pilot film identities, with
  five question facets per pair: choice, consequence, craft, attributed
  reception and premise/answerability checks.
- Thirty questions are development diagnostics; twenty are question-holdout
  inputs on different pairs. Films overlap, so this is not a film-disjoint
  generalization test. Old independently frozen question sets remain untouched.
- Inputs include public-topic discovery URLs. Most comparative wording is
  original and not established as a recurring/popular query. No answer keys
  were copied into evidence; no source labels or accuracy scores exist yet.
- The packet explicitly marks popularity_verified=false and
  independent_gold=false. Source-oracle review, external adjudication,
  source-version binding and scoring must precede any release-quality claim.
- One structural contract test passed: 50 distinct questions, 10 distinct
  pairs, ten film IDs, correct split counts and required provenance fields.
- File: backend/tests/fixtures/recovery-question-design-v1.json. This is a
  small question-only fixture, not raw film data or a test-label corpus.

## Frozen ten-film source export

- Added read-only exporter that binds the question design hash, film QIDs,
  current extraction selection, exact snapshot/contents hashes, source URL,
  revision, licence/attribution and latest decision version.
- Rejects missing/ambiguous film profiles, any approved source whose retained
  bytes fail verification, corrupt derived text and films with no eligible
  current text. Non-approved sources are explicitly excluded, not copied.
- Real container-namespace export: ten films, 487 retained passages, thirty
  development cases. Full local corpus:
  data/evaluation/recovery-ten-film-current-v1.json; fingerprint
  f368a110e693ef4438449113a93d522802275e75acc1ceafeb0b0c56ed1629de.
- Twenty held-out question inputs are stored separately, without duplicating
  the source prose: data/evaluation/recovery-ten-film-questions-heldout-v1.json;
  fingerprint c49000f4e04c074b52c482eb11f59a695bb0ef94205a47105fb975a666dd10a8.
- No database writes or source facts produced. One split contract test passed.
  Full-source answerability labels are still pending; none of these artifacts
  is independent gold, a production index, or evidence of passing retrieval.

## Source-oracle development review started

- Read complete current plot passages for Her, WALL·E, Endgame and Godfather
  before binding four choice/consequence development reviews. No new retrieval
  scores or model answers were used as labels for these questions.
- R01.choice partial: connection actions exist, but risk/motive comparison needs
  interpretation. R01.consequence provisionally complete: text identifies the
  surrogate encounter/tension and EVE's accusation plus reconciliation.
- R02.choice partial: Michael's protection motive is explicit, while the
  selected Endgame plot does not prove a symmetric family-vs-justice dilemma.
  R02.consequence partial: sacrifice and relationship cost are present, but
  loyalty/motive and causal interpretation require qualification.
- Added binder that validates the frozen corpus and passage hash, source/film
  scope, unique exact quoted substrings and offsets. It marks single-reviewer
  observations as non-independent and not release gold. One policy test passed.
- Local annotations/output are recovery-oracle-review-input-v1.json and
  recovery-oracle-review-v1.json under data/evaluation. They are physically
  separate from model inputs. Four of thirty development cases reviewed;
  twenty held-out questions remain unlabelled and unscored.
- These judgments are provisional, not a claim that all other passages in
  the corpus lack support or that a percent of the product is accurate.

### Source review extended to Jaws/Jurassic Park and 12 Angry Men/Shawshank

- Read all retained plot passages for these four films, independently of
  retrieved ranks for the new questions. Added six explicit source reviews:
  R03.choice complete, R03.consequence partial, R03.premise_check negative;
  R04.choice complete, R04.consequence partial, R04.premise_check negative.
- Important distinctions: investor certification/bribery vs the mayor's refusal
  to close beaches; sabotage vs a simple ignored-warning causal chain; doubt/
  acquittal vs proof of innocence; reported confession vs formal exoneration;
  interpersonal confrontation vs suppression of a witness by the warden.
- Each review records exact source spans and limitations. No claim is made
  that source summaries independently establish all film facts or legal rules.
- Binder now accepts multiple non-overlapping review batches and explicitly
  reports reviewed/total and pending case IDs. Combined local output:
  data/evaluation/recovery-oracle-review-combined-v1.json.
- Ten of thirty development cases now reviewed, twenty still pending. All
  twenty question-holdout cases remain unlabelled/unscored; no aggregate
  product accuracy or independently adjudicated gold is claimed.

### Plot-based development review: sixteen cases bound

- Read all retained 3 Idiots and PK plot passages; completed R05 choice,
  consequence and premise review, plus R06 Godfather/Shawshank equivalents.
- Provisional judgments: R05.choice/consequence complete, R05.premise_check
  negative; R06.choice complete, R06.consequence partial, R06.premise_check
  negative. Narrative and moral comparisons remain interpretations, not facts.
- PK's bombing account does not name who ordered it; no review invents that
  attribution. Shared Hirani credit is not evidence of identical ideological
  conclusions. Andy's financial activity is not treated as Michael's motive.
- Combined local review v2 now has sixteen cases, with fourteen development
  cases pending (craft/reception and two remaining premise checks). All twenty
  question-holdout cases remain unreviewed/unscored. Source-bound evidence
  spans passed the existing binder without changing the corpus.

### Remove duplicate project-local 0.6B model, preserve serving rollback

- Confirmed project story-server /api/ps had no loaded models. Removed its
  unused qwen3-embedding:0.6b tag through Ollama on **11435** only; model
  manager reported deletion. Its published stored size was 639,150,858 bytes.
- Separate embedding server **11434** still lists the original 0.6B and 4B
  digests, so the current serving rollback was not removed. No other model
  store, corpus data or experiment outputs were deleted. Replaying that model
  specifically on 11435 requires restoring the model there.
- Available disk nevertheless measured about 5.1 GiB after the operation;
  no claim is made that logical model removal yielded immediate physical
  reclaim. APFS/runtime effects were not established. Inference remains gated.

### Her/WALL·E craft, reception and premise review

- Read retained critical-response passages and production passages about voice,
  sound and animation for this pair. R01.craft is partial: WALL·E has concrete
  sound/animation methods; the inspected Her production material documents a
  recast and broad rationale, not equally specific voice-direction methods.
- R01.reception is provisionally complete: relationship credibility is
  explicitly debated for Her, and WALL·E's romance praised by an attributed
  critic. Other WALL·E objections concern humans/ecology; do not mislabel
  them as objections to the robot romance.
- R01.premise_check is negative: the plots distinguish a human/OS relationship
  from a robot/robot relationship. Both contain AI-related themes without
  sharing the question's assumed participant identities.
- Combined local review v3 has nineteen cases. Eleven development cases are
  pending, all held-out cases untouched. Binding checked all exact quotes
  against the frozen source text; these remain single-reviewer observations.
- No model run, live-serving change or new data acquisition was necessary.

### Twenty-five development cases reviewed

- Added six source-bound craft/reception reviews for R03, R04 and R05.
  Provisional complete: R03.reception, R04.craft/reception, R05.reception.
  Partial: R03.craft and R05.craft because technical/adaptation details do not
  alone establish the requested suspense or comedy mechanism for both films.
- Important source distinction: Shawshank's initial box-office disappointment
  is not critical rejection; 12 Angry Men's contemporary acclaim is separate
  from later canonization. Historical aggregator values are not release-era
  surveys. Social-impact commentary about education retains tentative wording;
  it is not proven policy causality.
- Inspecting headings revealed useful social-response material outside the
  earlier narrow legacy-heading inventory: 3 Idiots' Cultural impact and legacy
  sections and PK's Controversies. Heading-count audits must not suppress
  these source types when forming the research corpus.
- Combined local review v4 now covers twenty-five of thirty development cases;
  five remain. The twenty question-holdout inputs remain unreviewed/unscored.
  No inference, corpus mutations or independent-gold claim in this step.

## Development source-oracle checkpoint: all thirty cases

- Completed the remaining R02 and R06 source-support observations, retaining
  R02 craft/reception as partial rather than promoting general production
  metadata or emotional praise to specific family-staging/sacrifice evidence.
- R02.premise_check marked missing: no established source-bound exact viewer
  behavior percentage; do not invent a survey or claim worldwide absence.
  R06 craft/reception have provisional source support with attribution limits.
- Thirty reviewed development cases: thirteen complete, eleven partial, five
  negative/premise corrections and one missing. Ninety-three exact quoted
  spans are bound to frozen source hashes/offsets. No development cases remain
  pending in this packet; these counts are annotations, not model scores.
- Local artifact: recovery-oracle-review-development-complete-v1.json under
  data/evaluation. Single reviewer, no independent adjudication or release
  gold. Complete here means review coverage, not certainty of every judgment
  or exhaustive independent verification of all 487 retained passages.
- The untouched twenty question-holdout cases still require their own
  source-support labels before final scoring. Do not reuse development
  figures as held-out quality or train models on these evidence annotations.
- Requested user-side additional free disk, while continuing non-inference
  work. Last measurement ~5.9 GiB still below the model-job reserve.

## Lexical reference over all thirty development questions

- Reused the existing BM25 policy with per-film full-parent passages and
  section titles, preserving the frozen question text and source corpus.
  No model, network, source acquisition or database mutation.
- Evaluator verifies corpus fingerprint, review binding, exact case coverage,
  quoted spans and film scope. It does not return an answer-accuracy field
  other than null. One pure policy test passed.
- On thirteen provisionally complete cases, top five full passages per film
  contain 15/47 annotated source spans; top twenty contain 36/47.
  Partial cases: 13/33 at five, 23/33 at twenty. Negative cases: 2/13 and
  9/13 respectively; these last figures are not correct-abstention scores.
- Counts are annotated-span inclusion only, not all relevant evidence recall:
  annotations may omit alternatives or include multiple optional supports,
  and retrieving a whole parent makes coverage easier than a short window.
  These numbers cannot be compared directly to old window/MRR scores.
- Result remains local at data/evaluation/recovery-lexical-development-v1.json.
  It establishes a reproducible baseline for identical-input comparisons,
  not a model selection, release gate pass, or live site improvement.

## Full-pilot pinned 4B development run started

- Remeasured free disk at ~6.8 GiB, above the reserve; no new model download.
- Added opt-in fullparent representation to the existing dense-trial runner.
  It retains complete passage text and is versioned separately from fixed/
  aligned windows; four existing dense-trial policy tests passed.
- Started one resumable job over the frozen 487 passages and thirty
  development questions, Qwen3 embedding 4B at the previously pinned digest,
  1,024 dimensions, batch size two. This is not the held-out evaluation.
- Retained unified exec session: 8953. Cache:
  data/evaluation/recovery-ten-qwen4b-cache. Expected completed result:
  data/evaluation/recovery-ten-qwen4b-fullparent-v1.json.
- Initial progress reached 14/487 with disk holding near 6.8 GiB. These are
  live progress observations, not completion or throughput estimates.
- No serving switch or production index creation. Continue polling this same
  job; a quiet or expired observation does not justify another worker.

## Completed pinned 4B pilot and matched-input comparison

- Session 8953 exited successfully after 487/487 parents and 30/30 development
  questions. Retained ranking contract matches the frozen corpus fingerprint
  and exact pinned 4B digest above. Recorded embedding batches sum to 764.42
  seconds (not end-to-end API latency or steady-state per-query latency).
- Extended the existing inclusion scorer to validate retained rankings against
  exact questions, film scope, corpus fingerprint, finite scores and original
  source windows. A span counts only when its entire annotated range is inside
  a retrieved window. Seven pure scorer checks passed; these are integrity
  safeguards, not semantic quality proof.
- Top-five complete-case annotated-span inclusion: Qwen 4B **28/47**, compared
  with BM25 **15/47**. Partial-case spans: **21/33** versus **13/33**. Negative
  case evidence: **7/13** versus **2/13**, not a correct-abstention score.
- Reused the existing weighted RRF policy at the existing 3:1 dense/lexical
  weights and k=60, with ten retained candidates per lane. No new embeddings,
  model downloads, changed questions or annotation tuning. This control gave
  **28/47** complete, **20/33** partial and **7/13** negative spans: no overall
  improvement over dense alone. Do not promote this fusion as a quality win.
- Local result files: recovery-qwen4b-development-v1.json (initial v1 scorer
  metadata), recovery-hybrid4b-development-ranking-v1.json and
  recovery-hybrid4b-development-score-v1.json. The scorer now emits v2 metadata
  explicitly describing whole-span inclusion and non-inference scoring timing.
  Nine combined scorer/fusion policy checks passed. Raw prose/results stay local.
- Inspected concrete misses: R03.choice ranks thematic criticism over the Jaws
  mayor's beach/economy decision (annotated parent rank eight); Jurassic Park's
  investor-certification setup is outside retained top ten. R04.choice returns
  some genuinely relevant juror evidence but not the annotated opening vote;
  Shawshank's Tommy confession is outside top ten. Therefore annotation coverage
  is not exhaustive relevance accuracy, and deeper candidate retrieval plus
  query-specific evidence selection need evaluation before generation.
- R02.choice now retrieves Michael's protective killing proposal first and the
  Endgame Barton-family setup fifth, but Endgame's first two results are cast
  descriptions. The user's original failure is improved only in this offline
  diagnostic, not resolved in the running UI or certified as a useful answer.
- Disk measured about 5.1 GiB after completion. No further inference started
  below the six-GiB reserve; no source data or useful candidate models deleted
  to force a run. Held-out twenty questions remain unscored; live serving still
  has not switched to this candidate index. Goal remains incomplete.

## Cache-only candidate-depth diagnostic

- Added explicit `--cache-only` and `--candidate-limit` to the existing dense
  runner. Replay skips provider/model initialization and refuses missing cache
  entries rather than invoking inference. Retained vectors are checked for
  shape, finite values and nonzero norm. Candidate depth does not change the
  embedding contract/cache key. Disk reserve remains enforced before any new
  embedding batch; replay does not allocate model memory or download weights.
- Completed a depth-twenty replay from the same 487 parent vectors and thirty
  question vectors, with **zero new embedding batches**. Local artifact:
  recovery-ten-qwen4b-fullparent-depth20-v1.json.
- At twenty candidates per film, inclusion is **47/47** annotated spans on
  complete cases, **31/33** partial and **11/13** negative. This is development
  candidate coverage, not 100% retrieval relevance, answer correctness, precise
  evidence selection or held-out performance. Twenty is a large fraction of
  some film sources: Her has 23 parents, 12 Angry Men 24; Jurassic Park has 93.
  Do not advertise this as production quality or infer that all films have
  sufficient raw evidence. It supports testing a second-stage selector on
  this fixed pool rather than immediately reacquiring the same pilot sources.
- A twenty-deep weighted RRF control reduced top-five inclusion to **26/47**
  complete and **19/33** partial (negative unchanged 7/13). This control is not
  a candidate for promotion over dense-only. No weights were swept afterward.
- Adapted the existing source-bound reranker pool preparer to accept retained
  full-parent dense rankings. It validates exact source spans, snapshots,
  question/film identities and corpus fingerprint, then reuses the existing
  pool contract instead of introducing a parallel reranking engine. Prepared
  all thirty cases with twenty parents per side at
  recovery-ten-qwen4b-depth20-reranker-pool-v1.json; fingerprint
  b63275bd9661539d057cbf4194b37cb3b49307a380d469eef099227368ac44e6.
- Fifteen relevant pure-policy checks passed. No reranker/generator model was
  started, no serving configuration changed, and no held-out query was run.
  Next inference is the retained quantized 4B reranker on this fixed pool,
  once disk reserve is restored; report both useful selection and runtime,
  not merely schema success. More model downloads remain unjustified at the
  current headroom. Offline source-label and index-activation work can proceed.

## Source review for all twenty held-out question inputs

- Disk recheck remained about 5.0 GiB, below the inference reserve. No new
  model worker was launched and no useful model/source asset was removed.
- Extended the existing source-review binder with an explicit separately
  fingerprinted question packet. It validates source-corpus binding, packet
  hash, duplicate cases and development/holdout case-ID disjointness while
  preserving the original evidence-corpus fingerprint. Two policy checks pass,
  including split overlap and modified question packet rejection.
- Reviewed the retained plot, production, criticism and social/legal response
  prose for all twenty R07-R10 questions, without generating held-out model
  predictions. Local input batches recovery-oracle-heldout-input-v1 through v4
  bind at recovery-oracle-heldout-review-complete-v1.json: **13 complete,
  4 partial, 3 negative**, **56 exact source spans**, zero pending cases.
- These are provisional single-reviewer judgments, not independently
  adjudicated gold. The reviewer knows development results and films overlap
  the development set. Do not describe this as a blind or film-disjoint test.
  No question/evidence annotations were added to the retrievable corpus.
- Important limitations: Endgame/PK has no sufficiently documented symmetric
  writing-method comparison in the frozen source packet, and PK's loss of
  witnesses does not itself prove a changed protective strategy. Her/Shawshank
  supports letters as a motif, but a motif is not evidence of equally detailed
  voice/narration production methods. 3 Idiots' general satire/casting account
  is less specific about staging debate than Lumet's camera/lens explanation.
- Counterexamples reject an absolute anti-technology reading of WALL-E and
  Jurassic Park. A jury's acquittal is not omniscient proof, and shared motifs
  do not establish direct creative influence. Negative labels require a
  qualified response, not simply suppressing all sources.
- Source inspection also found reasons for further fact-level review outside
  this retrieval benchmark: 3 Idiots passage 9e77bc00-97b8-4880-97bb-11324584e42c
  describes Kai Po Che as a second Five Point Someone adaptation, whereas the
  author's own filmography associates it with The 3 Mistakes of My Life:
  https://www.chetanbhagat.com/other-works/films/ . Treat that as a flagged
  lineage discrepancy requiring review, not a silent correction to raw prose
  or a new operational Assertion. No canonical records were changed.
- Separately checked an unfamiliar 2026 Endgame rerelease reference against
  Disney's own dated account, which confirms the rerelease exists:
  https://thewaltdisneycompany.com/news/russo-brothers-avengers-endgame-doomsday/ .
  Do not reject current source material merely because prior model knowledge
  is older. That check does not independently validate every cumulative gross
  or rewrite the frozen evaluation evidence.
- Remaining: held-out model retrieval/scoring, reranker selection/generation
  quality, explicit candidate-index activation, current API/UI verification,
  broader 1,000-film reconciliation and final product go/no-go are not done.

## Explicit serving-index selection, not activated

- Added optional `ACTIVE_RETRIEVAL_INDEX_RUN_ID` configuration and explicit
  resolver `index_run_id`. Normal retrieval callers inherit the configured
  run; explicit offline model comparisons remain independent. Removed the
  implicit 0.6B argument from shared hybrid entry points so they do not bypass
  that pin. Unset configuration preserves legacy rollback behavior.
- A pin must select a complete index and preprocessing run in the requested
  collection/language, with an Ollama manifest-digest model contract, 1,024
  dimensions, nonzero matching completion counters and no reported failures.
  Wrong collection/language/model, failed/missing run or invalid revision
  fails closed, rather than selecting the latest candidate or another corpus.
- Verified against real isolated PostgreSQL `cinegraph_test`: a newer complete
  run does not displace a pin; invalid pins fail even with another complete run
  available. Twenty relevant activation/retrieval/comparison/config checks
  passed. These checks exercise selection metadata, not vector-row coverage
  or model accuracy. No working corpus tables or deployment settings changed.
- Cutover/rollback instructions and limitations are in
  docs/retrieval-index-activation.md. The offline 4B JSON/cache is not yet an
  admitted persisted serving index. Source/chunk parity, actual vector-row
  integrity, quality/latency review and API/UI verification remain required
  before setting the activation variable. No 4B promotion is claimed.
- Disk is now about 4.8 GiB. No inference was started below the reserve.

## Unresolved target identity proposals

- Read-only local IMDb discovery and retained reviewed cross-ID lookup produced
  proposals for 25 of 32 unresolved/outside target rows; 19 rows have at least
  one candidate with a retained cross-ID. These are **not approved identities**
  or proof the matched film belongs to the target collection. Seven rows had
  no title/year candidate under this search policy.
- A key warning: `Yip Man` also returned Iron Man, and `Kung fu` returned
  several equally scored candidates. The CSV's `Uri` year differs from the
  local IMDb year. Cross-IDs validate candidate identity only, not whether that
  candidate is the intended CSV row; title, year and source review remain
  necessary. Duplicate assertions/aliases are preserved, not treated as votes.
- Local report: data/reports/recovery-target-identity-proposals-v1.json.
  It includes reviewed assertion IDs and the sparse-index source hash. The
  derived title SQLite index is not independently fingerprint-bound to that
  hash by this diagnostic; treat all search results as review leads.
- IMDb TSVs remain uncompressed: their sparse index uses uncompressed byte
  offsets and plain gzip would break efficient random access. No data deleted.

### Identity lead spot checks

- AFI describes the 1950 film as Sunset Blvd. and notes the expanded title
  Sunset Boulevard: https://catalog.afi.com/Film/26513-SUNSET-BLVD . This
  supports rank 83's spelling variant, but the retained QID/IMDb binding must
  still be verified through its original assertions before acceptance.
- Hong Kong Film Archive identifies the 2008 Donnie Yen film as Ip Man:
  https://www.filmarchive.gov.hk/en/web/hkfa/2024/martial/pe-event-2024-martial-fs-film17.html .
  The festival listing uses Yip Man for the same director, actor and year:
  https://iffr.com/en/iffr/2011/films/yip-man . This supports rank 352's
  variant; the separate Iron Man fuzzy candidate is not evidence of identity.
- ZEE5 lists Uri: The Surgical Strike's theatrical release as 11 January 2019:
  https://www.zee5.com/movies/details/uri-the-surgical-strike/0-0-33204 .
  The frozen CSV says 2018. This is a discrepancy requiring review, not a
  reason to silently rewrite the source CSV or conflate release territories.
- Sony identifies Kung Fu Hustle as Stephen Chow's 2004 film:
  https://www.sonypictures.com/movies/kungfuhustle . The abbreviated CSV title
  `Kung fu` is still ambiguous by itself; retain alternative candidates until
  the CSV's other fields corroborate the intended work.
- No identity approval, canonical merge, snapshot acquisition or corpus
  membership change occurred in these checks.
- Follow-up against the frozen CSV's own director/cast columns narrows the
  earlier ambiguity: rank 777 records Stephen Chow as both director and lead,
  matching Sony's Kung Fu Hustle description; rank 352 records Wilson Yip
  and Donnie Yen, matching the Hong Kong Film Archive entry. Rank 83 records
  Billy Wilder and William Holden, matching AFI/Paramount. Rank 130 records
  Aditya Dhar and Vicky Kaushal, consistent with the identified Uri film but
  retains the 2018/2019 year discrepancy. These independent fields support
  the proposed matches; they do not mutate the frozen CSV or themselves prove
  the retained QID assertion chain and collection admission.

## Local 4B reranker run resumed

- At the user's direction, removed the unloaded `qwen3:8b` generation model
  through the Ollama server on port 11435, after verifying that server's model
  store was this project's `data/ollama-models`. The 4B generation model and
  the global Ollama store were untouched. The removed model is recoverable by
  downloading it again; its model weight is not in Git. Free disk measured
  12.45 GiB after removal (previously 7.59 GiB).
- Started the existing quantized Qwen 4B MLX reranker against the fixed
  twenty-parent-per-film, thirty-question development pool, with film title
  and source section context, checkpoint/resume enabled. Output is local at
  `data/evaluation/recovery-ten-qwen4b-reranker-development-v1.json` and the
  live execution session is 44487. The first sandboxed launch could not
  access Metal and exited before output; the GPU-enabled retry is running.
  No quality result or live-site change is claimed until it completes and
  its selected passages are evaluated against the source-bound review.

## Completed 4B reranker development comparison

- Session 44487 completed all 30 questions successfully. The source-bound
  converter verified the exact capture, candidate sets, film identities and
  retained full-parent text before scoring. On 13 provisionally complete
  cases, top-five inclusion improved to **42/47** annotated spans versus
  **28/47** for the same Qwen 4B embedding ranking alone. Partial cases were
  **23/33** versus **21/33**; negative cases **11/13** versus **7/13**.
  Negative-case inclusion is not an abstention score. These labels are
  single-reviewer development annotations, not exhaustive relevance or
  writer-answer accuracy; held-out evaluation remains unrun.
- Four complete cases still missed at least one annotated span: R01.reception
  3/4, R03.choice 3/4, R03.reception 3/4, R04.craft 1/3. More passages may
  also be relevant than were annotated. Inspect sources before declaring
  factual correctness or treating retrieved prose as a finished answer.
- Summing measured sequential per-film reranking gives a median **121.4 s**
  per two-film question, maximum **143.1 s**, and total **3,614.1 s** across
  30 questions, excluding embedding and generation. This fails interactive
  latency needs. Do not deploy the 20-parent-per-side reranker as-is.
- Local files: recovery-reranker4b-development-ranking-v1.json and
  recovery-reranker4b-development-score-v1.json. The model weight observed
  SHA-256 after launch was `8003a82d273cfbf540f3dd96775dd9065d438a9d91ca4983e7a9c4d0dd9e1448`;
  the checkpoint itself records a model path rather than that hash, so this
  is an observed file hash, not a fully pinned run contract.
- Next: investigate faster candidate selection/batching and compare against
  the same development evidence without tuning on the held-out questions;
  separately fix grounded generation. Neither serving nor user-facing answers
  have been changed by this offline experiment.

### Candidate-depth latency diagnostic

- Replayed the completed full-pool scores while restricting each film to the
  first 5, 8, 10, 15 or 20 dense candidates before selecting five. For the 13
  provisionally complete development cases, annotated-span inclusion was
  respectively **28/47, 36/47, 38/47, 42/47, 42/47**. These are retrospective
  development simulations, not an unbiased model-selection evaluation.
- Directly reran `R03.choice` at depth 10 on the same 4B reranker: **43.2 s**
  summed two-film scoring versus **118.5 s** in the depth-20 run. Both sides'
  top-five IDs agreed with the restricted replay for this question. This is
  one pair, not a latency distribution or an end-to-end request benchmark;
  even this timing is too high for the intended interactive workflow.
- The result supports exploring a smaller reranker pool, but does not prove
  equivalent quality across questions or justify promoting it. The explicit
  question-holdout remains unused for tuning. Local retained capture:
  `recovery-ten-qwen4b-depth10-reranker-pool-v1.json`; single-question result:
  `recovery-rerank4b-depth10-r03-choice-v1.json`.

### Bounded MLX allocation-cache check

- Repeated that same depth-10 question with the 128 MiB MLX allocation cache
  retained until the end of each film instead of explicitly cleared after each
  passage. Single-run measured scoring was **43.95 s** versus **43.16 s** with
  per-passage clearing; reported peak MLX memory was **2.59 GiB** in both.
  Rankings were identical on both sides. This one-pair observation does not
  establish general performance equivalence, but provides no evidence to keep
  the added runtime option. The temporary code change was removed.
- Local result: `recovery-rerank4b-depth10-r03-cached-v1.json`. This experiment
  does not address batching, prefix sharing, different model architecture or
  user-facing end-to-end latency; those remain separate options to evaluate.

### Two-passage batch diagnostic

- Measured single-passage versus right-padded two-passage inference on the
  same depth-10 R03.choice pool and locally installed 4B model. Per-passage
  scoring took **42.73 s**, batch-of-two **86.36 s**, on 20 total passages.
  The first five IDs matched for both films; maximum yes/no logit-difference
  delta was **0.0625**. Peak MLX memory across both stages was 2.71 GiB.
- This single-case result rejects this particular naive batching attempt as a
  performance improvement; it does not prove batching is universally slower.
  Variable-length padding, launch order, thermal and memory conditions could
  affect timing, and were not separately isolated. It does not validate model
  relevance, held-out quality or end-to-end latency. Do not enable in serving.
- Local raw scores stay in `recovery-reranker-batch2-r03-v1.json`; the optional
  diagnostic script is `scripts/benchmark_reranker_batch.py`. Further options
  include shorter source-preserving windows and prefix reuse, each requiring
  measured score/relevance and memory comparisons.

### Reranked evidence to grounded answer: negative result

- Ran the local pinned 4-bit Qwen3 4B instruction model against the reranked
  R02.choice Endgame/Godfather source pool, using the existing constrained,
  citation-first span-ID trial. A shape adapter now accepts the validated
  full-parent reranker export while recording its digest; no UI route changed.
- The output passed its citation-format validator, but source-aware inspection
  **failed semantic quality**. It claims Natasha prioritizes allies over a
  wider justice and casts her sacrifice as opposing justice; the cited cast
  passage does not establish that conflict. It claims Michael's assassination
  protects family, but its chosen short citation stops before that event and
  does not establish the claim. Its comparison falsely forces symmetry and
  misframes both films as fighting a systemic injustice. Valid span IDs do not
  prove entailment. Do not show or deploy this output as a grounded answer.
- The single generation took **94.5 s** with 4,336 input tokens, excluding
  retrieval/reranking. This is not an interactive end-to-end latency. The
  retained local output is `recovery-reranked-4b-answer-r02-v1.json`.
  Ten grounded-trial policy checks passed; they do not validate interpretation.
- Next work must separate evidence observations from comparative inference,
  verify claims and citations semantically, and measure a smaller grounded
  context. Do not infer that a larger candidate pool or valid JSON fixes
  generation. Held-out source questions remain unused for tuning.

### Second grounded-answer diagnostic: Her and WALL·E

- Reused the same ranked-passage, constrained citation-first setup on
  R01.choice, asking which actions turn isolation into connection and what is
  at risk. It consumed 3,459 prompt tokens and took **86.3 s** for generation
  alone. The local output is `recovery-reranked-4b-answer-r01-v1.json`.
- The validator rejected the unfinished scene experiment; the model exhausted
  its output budget mid-sentence. Its proposed scene also reused WALL-E and
  EVE instead of making an original writing exercise. The answer describes
  Theodore's failed surrogate encounter as physical intimacy with Isabella,
  and asserts the seedling risks EVE's function without establishing that
  causal claim. These are unsuitable user-facing interpretations, irrespective
  of formatting. Narrative support must be checked against the source passages,
  and episode descriptions must not assign actions to the wrong participant.
- Alongside the previous Endgame/Godfather failure, this is evidence of a
  repeated answer-generation problem, not proof every question will fail.
  No live generator or site configuration was changed.

### Matched-packet 8B generation comparison

- Restored project-local `qwen3:8b` after confirming sufficient disk space;
  its digest matched the previously recorded
  `500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41`.
  Using the existing Ollama draft experiment, the Her/WALL-E 8B packet was
  verified byte-equivalent after parsing to the earlier `qwen3:4b` packet.
  Same prompt/schema and generation settings; this is not the separate MLX
  4B instruction checkpoint trial described above.
- The 8B draft finished in **101.1 s** with `done_reason=stop`, compared with
  approximately **61.8 s** for 4B on that earlier run. It failed the exact
  quotation validator: B1 changes source text by ending a quote after
  `designated` with a full stop that is absent at that location. A valid JSON
  response or completed output is not evidence of factual support.
- The source-aware review also found an important omission: its generic
  comparison does not clearly distinguish a human/AI relationship from the
  robot/robot relationship. It makes broad claims about motivations and
  isolation that need stronger support. The result is **not approved for
  serving**. The local artifact is `recovery-her-walle-draft8b-v1.json`.
- This is one matched-packet example, not a general 4B/8B model benchmark.
  It shows that model size alone has not resolved grounding or interactive
  latency in this setup. More reliable citation selection, claim review,
  prompt/context design and broader independent evaluation remain necessary.

### Staged 8B observation/comparison diagnostic

- Reused the exact Her/WALL-E packet from the matched 8B draft; asked for one
  per-film observation, exact quote and limitation in separate calls, then
  compared the observations in a third call. The diagnostic, not a serving
  path, is `scripts/staged_recovery_draft.py`; output remains local at
  `recovery-her-walle-staged8b-v1.json`.
- All three calls ended normally and the two quotes matched visible source
  substrings. The summed local request times were **62.5 s** (24.1 + 22.6 +
  15.8), versus **101.1 s** for the previous one-call draft. These timings
  include different model loading/keep-alive and output lengths; they are not
  a controlled end-to-end latency comparison.
- Semantic review **failed**. Each observation generalizes about artificial
  companions despite evidence for particular characters; the WALL-E statement
  converts a filmmaker's intended theme into a general behavioral claim without
  attribution. The synthesis repeats the generalization and still misses the
  human/OS versus robot/robot distinction and concrete relationship choices.
  Therefore exact quotes and staged prompting alone did not produce a useful
  or reliably supported writer's answer. No live feature was enabled.

### Participant/action prompt and source-label correction

- A revised staged prompt requested named participants, concrete source-stated
  actions and source type. Its first run (local `recovery-her-walle-staged8b-v2.json`)
  labeled two plot excerpts as filmmaker statements. Inspection found that the
  experiment's input omitted section headings; the result cannot fairly test
  whether the model can classify source type when that information is present.
- The diagnostic now takes the original selected-evidence packet, verifies
  text, film and snapshot identity against the baseline pack, and supplies the
  corresponding section title. It records the selected-packet hash and prompt
  version. No source text or operational assertions were changed.
- In the corrected v3 local run, both quotations matched and both source types
  were identified as plot. The synthesis cautiously said its two selected
  observations could not answer the question. That limitation is appropriate
  for those two observations, but the choice of observations omitted relevant
  relationship material elsewhere in the provided packet. It still did not
  name the robot/robot contrast, and its phrasing about what the *film* does
  not provide goes beyond the narrower evidence-selection gap. Thus this is
  not a useful complete answer and is not a release-quality pass.
- Three model calls totaled **68.6 s** on this local run. Local output:
  `recovery-her-walle-staged8b-v3.json`. This is a single development example;
  next experiments need query-specific evidence selection and source-bound
  claim verification, plus a separate held-out assessment and latency work.

### Two-observation selection experiment

- On the same development question and source pack, the offline diagnostic
  requested two distinct, question-relevant source-quoted observations per
  film rather than one, with explicit film identifiers. The model and source
  hashes remained pinned; the optional setting does not change live serving.
- The four quotes all matched their source passages. The selected observations
  included Samantha's surrogate attempt and WALL-E and EVE's reconciliation,
  but also a blind date and a plant rescue whose relevance to the question is
  less direct. The model then declined to make any meaningful comparison,
  even though the more relevant observations support a limited comparison.
  It also repeated unjustified claims about what the film does not provide.
- Result: **not a useful answer and not a release pass**. The model's cautious
  response is preferable to invented evidence but is still an incorrect product
  outcome. Four exact quotes are not four verified interpretations, nor is a
  single development case a benchmark. Total measured model-call time was
  **96.8 s**, excluding orchestration. Local output:
  `data/evaluation/recovery-her-walle-staged8b-v4.json`.
- More observations alone did not solve question interpretation or entailment;
  retrieval, claim selection and model reliability require evaluation on
  multiple frozen examples before any serving integration.

### Freeze for the previously unranked question set

- Before generating predictions for the 20 held-out questions, freeze the
  development-selected control: Qwen3-Embedding 4B Q4_K_M at digest
  `df5bd2e3c74cd8d069d21dc038f1b359fcdc9458fce1c99bd43c9eb1518ff907`,
  1,024 dimensions, full-parent passages, original question, exact cosine,
  per-film scope, 20 candidates. Report top-five and top-twenty span inclusion
  against the separately retained review; compare a same-input BM25 control.
- No reranker is selected for interactive serving: the development depth-20
  reranker took a median 121.4 seconds per question and the faster depth-10
  single-question test took 43.2 seconds. Neither met the proposed latency
  budget. The dense configuration is a diagnostic control, not a declaration
  that retrieval or end-to-end answers are ready.
- The 20 questions and source annotations were inspected during source review
  by a single reviewer, with films overlapping the development set. This is a
  previously unranked question set, not an independent or film-disjoint blind
  test. Freeze this protocol before inspecting its rankings; do not tune on its
  results or silently revise the existing annotations after scoring.

### Frozen question-set retrieval result

- The local 4B run completed all 20 questions using the original 487 cached
  full-parent document vectors and 20 newly computed query vectors. The
  separate question packet was fingerprint-checked and bound to the original
  source corpus; it was not used as evidence or to alter the cache contract.
  Ten two-query batches took approximately 21.3 seconds total, including a
  15.2-second first batch; this is not request p95 or end-to-end latency.
- On the 13 cases provisionally marked complete, the fixed 4B configuration
  included **27/40 annotated spans at five** and **40/40 at twenty**, versus
  lexical **8/40** and **25/40**, respectively. All annotated spans were in
  the top five on both sides for **6/13** complete cases. This stricter number
  is not necessarily facet coverage: annotations can include alternative or
  extra supporting spans, while unlabelled alternatives can also be valid.
- The four partial cases included **4/10** spans at five and **8/10** at
  twenty; the three negative cases included **1/6** and **4/6**. These are
  evidence visibility numbers, not premise-correction or abstention scores.
  This result does not demonstrate useful generated answers or justify a
  serving switch. The known slow 4B reranker remains outside this frozen arm.
- Raw rankings and scoring artifacts remain local under `data/evaluation/`:
  `recovery-qwen4b-heldout-depth20-v1.json`,
  `recovery-qwen4b-heldout-score5-v1.json`,
  `recovery-qwen4b-heldout-score20-v1.json`, and
  `recovery-lexical-heldout-v1.json`. The explicit question-packet adapter
  checks fingerprints, case overlap, film scope and review/ranking binding;
  twelve focused integrity and ranking tests passed. No operational corpus,
  live index or site behavior changed.

### Explicit 4B writer-index build path

- The writer-catalog builder previously always constructed the legacy 0.6B
  profile. It now accepts an explicit pinned profile; its CLI requires a 4B
  or 8B tag and a full model digest. The digest is checked before chunk
  creation, during model calls and before import. Programmatic callers that
  omit the profile retain the previous behavior for compatibility.
- An explicit 4B run against isolated `cinegraph_test` and real local Ollama
  built two fixture-film vectors, imported them into pgvector, resolved the
  exact new index and retrieved evidence for both films. A deliberately wrong
  digest was rejected. The isolated test also exercised cache reuse and source
  integrity checks. No working-corpus records or serving variables changed.
  Thirteen focused policy tests and the isolated integration test passed;
  the environment emitted a PyTorch/NumPy compatibility warning and a Click
  deprecation warning, neither of which was investigated in this milestone.
- This establishes a path to build an inactive 4B writer index, **not** that
  the ten-film diagnostic vectors were imported or that 1,000 films are
  eligible. The builder uses a different chunk representation from the frozen
  full-parent experiment. Review collection admission, row-level lineage and
  retrieval/answer quality before any working-corpus build or activation.

### Current 1,000-film readiness, with capture-status correction

- Re-ran the source inventory against the working corpus using a read-only
  repeatable-read database transaction and read-only snapshot-volume mount.
  The older inventory policy did not check snapshot fetch status, unlike the
  writer index builder. Manifest v2 now requires `fetch_status=success` and
  records it explicitly; unsuccessful or unknown statuses fail closed.
- Under that corrected rule, **10 of 1,000 collection films** have at least
  one currently approved, byte-verified source with intact passages. The
  remaining **990** have current sources whose listed exclusion is semantic
  use not approved. This is source-build eligibility, not identity accuracy,
  independent content validation, a release-rights grant or a serving index.
- Reconciled the new manifest with the unchanged supplied CSV and historical
  target mapping: **968** rows have one current historical-QID candidate,
  **32** remain unresolved or outside the collection, and **10** target rows
  have an eligible candidate. The reconciliation did not perform or write
  target identity approvals. The CSV has an additional row outside the frozen
  1,000-row target.
- The configured `writer-catalog-v1` collection does not currently exist in
  the working database. The ten source decisions were documented for local
  experimentation; they must not be silently treated as permission to publish
  them or as approval for the other 990 sources. No bulk approval, collection
  creation, index build or activation was performed.
- Local artifacts: `data/reports/corpus-build-input-2026-11-21-v2.json`
  (manifest SHA-256 `43ecc82ebf56665e7d83a20d718b978195c49b6b6a81441b1c0e4f07264fe14c`)
  and `data/reports/recovery-target-reconciliation-v3.json` (report SHA-256
  `7d0a1f57de92400699843530b8cc6fc770c25faf6b4c0829955b23a64996bf20`).
  Four focused admission/reconciliation checks passed. Older v1 inventories
  remain retained but are not equivalent to the corrected policy.

### Vector-row and source-lineage audit

- Added a read-only index audit that checks actual vector membership against
  currently approved eligible chunks, run counters, pinned model and cache
  contracts, chunk/parent/vector hashes, finite nonzero vectors, current
  passage selection, and retained snapshot bytes. It does not activate an
  index, verify model inference, establish relevance, or grant publication
  rights. The checker streams vector rows but retains chunk identities and
  current passage records in memory; its scalability beyond this catalog has
  not been measured.
- A real 4B fixture index in isolated `cinegraph_test` passed. The same test
  deliberately changed a vector's content hash and separately removed a
  vector while keeping the run's counters intact; both failures were detected.
  No working-database mutations were used in these tests.
- A read-only check of the existing legacy index
  `0adc1904-7788-4f65-8622-1e449b1f612e` found 24,194 vector rows against
  111 chunks currently approved within that original chunk run. The other
  24,083 rows were outside current semantic approval; those 111 approved
  chunks referenced passages no longer selected as current. Counters and the
  current document-cache key did not match the approved set, and the old
  model-revision format did not satisfy the new pinned-manifest contract.
  All 1,000 snapshot files checked by this command passed byte verification.
  These are current observations, not proof that a source's contents are true.
- The live hybrid retrieval query filters by semantic-use approval, but this
  audit does not establish that it also excludes superseded passage revisions.
  Inspect and fix that read path before treating stale evidence as safe to show.
  No model or index was activated or deleted.

### Current-revision retrieval guard

- Inspection confirmed that both hybrid/lexical retrieval and the standalone
  semantic retrieval path filtered by rights but did not require the selected
  current passage. They could therefore return an approved older revision.
- Both paths now restrict candidates to `current_passage_rows` for the film
  and require the chunk's snapshot, film and language to match its parent.
  The anthology fallback uses the same current-passage restriction. The
  standalone semantic path now also checks pinned Ollama manifest digests
  when the model record has one, matching the hybrid path.
- An isolated `cinegraph_test` run with real 4B vectors first retrieved current
  evidence, then inserted a newer successful capture and verified that the
  lexical, semantic, hybrid and standalone paths returned no stale evidence.
  The check passed; 14 existing research-read integration checks also passed
  in the separate integration container. The initial host-side attempt at that
  wider suite could not collect because `mwparserfromhell` was absent in the
  Conda environment; no package installation was needed in the test image.
- This change intentionally yields no old evidence when the newer source has
  not yet been extracted/indexed. It does not create a current index, measure
  the latency of this additional current-passage lookup, or improve generation.
  The running API image was not rebuilt in this step and still runs its prior
  code until explicitly rebuilt/restarted.

### Target identity review enriched with credits

- Built an append-only local review report by joining the 32 unresolved target
  rows and their retained IMDb candidate IDs to the frozen CSV's director and
  four credited names. It uses the existing sparse IMDb indexes and validates
  the CSV, reconciliation and proposal hashes before reading candidate credits.
  Exact normalized-name matches are evidence for review, not automatic merges;
  absent principal credits or alternative spellings are not proof of a mismatch.
- On this historical proposal set, **17/32 rows** have a candidate with a
  director-name match and **20/32** have a candidate with at least one cast
  match. The sets overlap and do not represent resolved films. For example,
  `Kung fu` matches Stephen Chow and all four listed performers to the candidate
  *Kung Fu Hustle*; `Uri` matches Aditya Dhar and all four performers but the
  CSV's 2018 and candidate's 2019 remain a visible conflict. The report also
  retains all candidate cross-ID assertions, including duplicate assertions,
  and does not treat them as independent votes.
- Artifact: `data/reports/recovery-target-identity-credit-review-v2.json`,
  report SHA-256 `96ca03a14539fccf4c0ecfdf127af18775167210dd0176a3ad4b8e87c6fbf535`.
  IMDb source hashes are carried from sparse-index metadata and the adapter
  checks source size and modification time; it does not rehash the large dumps
  on each run. This is based on the earlier frozen proposal report, not a new
  live search, and does not approve identity or create collection membership.

### Ten-film real-source 4B pgvector canary

- Exported snapshot descriptors in a repeatable-read, read-only transaction.
  The verifier matched the frozen pilot's 487 passages to current passage IDs,
  exact content, source hashes, revision, section locator/title/ordinal,
  extraction version, attribution, licence and semantic-decision version;
  all 10 retained source files passed their byte hashes. Descriptor fingerprint:
  `07f24ec99fc41ca0ff3d373c256ceabd27617403be080bdc5b20c57de57a30c3`.
  A second run after adding the metadata checks produced the same fingerprint.
- Replayed the actual text and source descriptors into a fresh isolated schema
  in `cinegraph_test` using the existing source/decision tables. No questions or
  annotations were inserted as evidence, and the working corpus was not
  changed. The replay does not copy the original passage citation markers;
  it validates snapshot-level provenance, not reference-level citation parity.
- The first attempt stopped before indexing because a fixture inserted a Film
  with no required original-language value. Removed the unnecessary Film row,
  rather than guessing a language. The second run created 511 chunks, excluded
  seven, embedded and imported **504 vectors from ten films** using the pinned
  Qwen3 4B model, and passed the index integrity audit. Total test wall time was
  **737.7 seconds**, including setup, embedding, import, audit and four query
  calls. The isolated schema was cleaned up; this is not a persistent or active
  writer-catalog index.
- Inspected two development questions against their returned source passages.
  For the user's Endgame/Godfather question, the Godfather results included
  relevant protective choices, while Endgame's direct sacrifice passage was
  fourth after a lead and two broadly positive reviews. For Her/WALL-E, Her's
  first three plot results were relevant, but WALL-E's top five lacked the
  first meeting and included several less direct writing/theme passages.
  These are not complete, independently rated answers; the result does not
  pass the product-quality or generation gate. The reported per-film query
  embedding timings were approximately 325–337 ms and ranking 18–181 ms for
  these four warm calls, not a measured p95 or end-to-end answer latency.
- Local report: `data/evaluation/recovery-ten-film-pgvector-4b-canary-v1.json`,
  file SHA-256 `169365757c1a508295306fccc1c63520b76e0f7404d7ab398630efad5c02956e`.
  The index was not activated. Free space after the run was about 8.6 GiB;
  the cause of the decrease has not been established, so retain the six-GiB
  reserve and remeasure before further model work.

### Question-only section-reserve development ablation

- Tested a small offline selector on the frozen 30 development questions and
  retained 20-deep 4B full-parent rankings. It reads only the question text:
  obvious reception, production or plot terms request at most two matching
  section leads in the top five; unrecognized questions retain dense order.
  It does not read the question's preassigned facet or source-review labels
  during ranking and never claims that a section match answers the question.
- Against the same single-reviewer span annotations, complete-case top-five
  inclusion rose from **28/47 to 32/47**; partial-case inclusion rose from
  **21/33 to 25/33**, while negative-case inclusion stayed **7/13**. Five cases
  gained annotated spans and `R06.reception` lost one. These counts are not
  answer accuracy, exhaustive recall, abstention quality or independent
  generalization. Routing was plot for 11 questions, reception for six,
  production for two and unchanged for 11.
- Both full source rankings and their scores stay local in `data/evaluation/`:
  `recovery-section-reserve-development-ranking-v2.json` and
  `recovery-section-reserve-development-score-v2.json`, with the original
  dense ranking fingerprint in the new ranking. Two deterministic policy
  checks passed. This is an exploratory development result; it has not been
  evaluated on a fresh independent set or on the 504-chunk pgvector index,
  and has not been integrated into the live site. Do not tune or rerun it on
  the already examined question-holdout set as though that were a fresh test.

### Three further individual local source reviews

- Rechecked [Wikipedia's reuse guidance](https://en.wikipedia.org/wiki/Wikipedia:Reusing_Wikipedia_content)
  and the [CC BY-SA 4.0 deed](https://creativecommons.org/licenses/by-sa/4.0/).
  Attribution, licence and change notices remain necessary; embedded quotations,
  images and other third-party material may have separate restrictions. This is
  not a determination that the application is cleared for commercial use.
- Individually inspected retained source leads, exact current revisions and
  snapshot hashes, then recorded AI-assisted decisions for local semantic
  experiments only through the local operator API:

| Film | Snapshot | Revision | Decision version |
| --- | --- | --- | ---: |
| The Dark Knight (2008), Q163872 | `225f5329-d90f-4be3-b130-f55b1147b731` | `1384066085` | 2 |
| The Godfather Part II (1974), Q184768 | `1d54b084-82e0-40f7-926a-966f0a28cda1` | `1381447815` | 1 |
| The Return of the King (2003), Q131074 | `3664504b-29a7-47f5-be15-5cad91eb3992` | `1385650960` | 1 |

- The Dark Knight's version 2 only clarifies that the review was AI-assisted;
  version 1 remains in the append-only history. Each API approval rechecked
  snapshot-file integrity. These notes describe intended local scope, but the
  existing semantic-use decision schema does not technically enforce a
  local-only sub-scope. No index was built or activated and no publication or
  canonical identity claim was made.
- Fresh read-only inventory: **13/1,000 collection films** have at least one
  source eligible under the current semantic-use policy. Reconciliation also
  reports **13 target rows with an eligible candidate**, not 13 fully verified
  catalog identities; 968 candidates and 32 unresolved/outside rows remain.
  Local files: `data/reports/corpus-build-input-2026-11-22-v1.json` and
  `data/reports/recovery-target-reconciliation-v4.json`. The source decisions
  are database-local and are not included in Git.

### Seven additional source-level checks

The retained leads were individually inspected for film identity and the
operator endpoint rechecked each snapshot's file integrity. These are
AI-assisted decisions for local semantic experiments, not a review of every
claim in each article or independent approval of the catalog identities.

| Film | Snapshot | Revision | Decision version |
| --- | --- | --- | ---: |
| Pulp Fiction (1994), Q104123 | `99251813-64ff-47aa-ae62-3af6e392fbd3` | `1385190039` | 1 |
| Schindler's List (1993), Q483941 | `c46e103e-212a-43d6-a762-06ed79e27804` | `1383963801` | 1 |
| Inception (2010), Q25188 | `2faa24ab-6748-4468-96da-961b550ba45b` | `1385246876` | 1 |
| Fight Club (1999), Q190050 | `c134fb5e-c566-4790-bab6-c26e4b7af49e` | `1385277614` | 1 |
| The Fellowship of the Ring (2001), Q127367 | `a384c501-0695-414d-84c8-85ac6426ee9a` | `1385779646` | 1 |
| Forrest Gump (1994), Q134773 | `38c82488-3459-431e-b051-3b28ce121d95` | `1384754400` | 1 |
| The Matrix (1999), Q83495 | `a56c1c87-f0ef-4eee-b434-5f3827a16929` | `1385789437` | 1 |

The local inventory now reports **20/1,000 films** with an eligible source,
and the frozen-target reconciliation reports **20 target rows with an eligible
candidate**, 968 candidates overall, 32 unresolved/outside rows and zero
approved identities. Inventory and reconciliation are stored locally at
`data/reports/corpus-build-input-2026-11-22-v2.json` and
`data/reports/recovery-target-reconciliation-v5.json`. As above, the operator
API records the configured operator email; the decisions were made by the AI
assistant and are explicitly identified as such in their notes. The existing
schema does not technically constrain approval to local use. No vectors or
live retrieval settings changed.

The 504-vector canary's saved matrix lacks a complete durable chunk-to-row
mapping; it must not be reused as a serving index based on assumed order.
A future build must persist and validate that mapping, model fingerprint and
source hashes before the temporary index is removed.

### Vector mapping safeguard: small real-component check

- The next ten-film canary now retains its vector cache and writes a separate
  local mapping before the temporary database schema is removed. The mapping
  binds each row to its chunk, parent passage, film, source snapshot/hash,
  source location, exact model-input hash, preprocessing run, cache key and
  pinned model digest. It also records the matrix's hash, shape and dtype.
- The mapping writer was checked on a **two-film fixture** using the real
  Qwen3-Embedding 4B Q4_K_M digest and isolated `cinegraph_test` PostgreSQL.
  Both saved matrix rows exactly matched the corresponding pgvector rows;
  the existing fixture's source-integrity, index and retrieval checks passed.
  This does not validate film answer relevance and cannot recover the old
  unmapped ten-film matrix. It does not yet implement a standalone importer
  that reconstructs an index after the original schema is removed.
- The new ten-film canary itself has not been rerun. Avoid repeating its 504
  embeddings solely to demonstrate the mapping; use the next substantive
  corpus/retrieval experiment to validate it at full size, with disk headroom
  and explicit source coverage recorded first.
