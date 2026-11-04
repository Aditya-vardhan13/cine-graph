# CineGraph catalog expansion: execution plan v1

Status: execution underway, updated 3 November 2026. This is an operational
sequence, not a claim that the catalog is ready, benchmark data is
product-cleared, or answers are writer-grade.

Related: [catalog and narrative data plan](catalog-and-narrative-data-plan-v1.md),
[architecture and test gates](core-architecture-and-test-gates-v1.md),
[open narrative data audit](open-narrative-datasets-audit-2026-11.md), and
[RAG experiment program](rag-experiment-program-v2.md).

## 1. Decision

Build one repeatable, source-aware film intake pipeline first. A large title
file, benchmark download, or successful embedding run is not a ready catalog.
The sequence is:

```text
admin submits titles / permitted source links
  -> resolve identity and disambiguate
  -> capture authorized source snapshots locally
  -> parse into source assertions and narrative passages
  -> validate identity, provenance, rights, fields and conflicts
  -> review exceptions; publish eligible facts and evidence
  -> prepare versioned chunks and incrementally index eligible passages
  -> evaluate retrieval and writer-facing answers on frozen questions
```

First target: a reviewed 100-film pilot. Next: a versioned 1,000-film reference
collection. Neither is the same scope as the current 2,586-film working
catalog. We do not need 100,000-film infrastructure now.

Two distinctions govern the work:

1. SemEval and MF² are evaluation resources, not bulk additions to the product
   catalog. Their texts, questions, claims and labels do not automatically
   become product evidence.
2. “In the database” is not “correct, reviewed, attributable, reuse-eligible,
   indexed, or useful for this question.” These require separate states and
   denominators.

## 2. Audited starting point

The local readiness report covers 2,586 records. In the frozen first-100
selection from `imdb_top_1000.csv`, 77 rows match catalog title and year
exactly; 23 are unique IMDb-ID crosslinks. A later SHA-256-bound decision
artifact accepts their same-work mapping for **pilot-list membership only**;
the frozen manifest and operational identity records remain `review_required`
and are not merged. All 100 have resolved director, cast, writer and
release-event-year assertions and nonzero stored embedding vectors; 99 have a
plot passage. Field-level coverage is uneven:

| Pilot coverage indicator | Films / 100 | Meaning |
| --- | ---: | --- |
| Exact title + year match | 77 | Candidate match, not full identity review |
| Unique IMDb-ID crosslink | 23 | Accepted for pilot membership only; not merged and not content approval |
| Resolved director / cast / writer assertion | 100 / 100 / 100 | Presence only; not complete-credit accuracy |
| Release-event year / legacy profile release date | 100 / 19 | Event year exists; old profile date mostly empty |
| Runtime in legacy profile field | 19 | High-priority projection/presentation gap |
| Plot / production / reception passage | 99 / 96 / 100 | Presence only; not relevance or rights clearance |
| Themes / legacy passage | 46 / 50 | Uneven depth; no single completeness score |
| Character gap absent in readiness report | 43 | Actor-to-character coverage materially incomplete |
| Indexed at least once | 100 | Does not prove useful/current retrieval |
| Snapshot has recorded license/attribution indicators | 100 | Not a legal clearance decision |

These are audit-artifact counts, not human correctness findings. The title
input is a historical CSV, not a certified current IMDb ranking. IMDb local
data remains non-commercially restricted; do not carry its fields into a paid
product without separately valid rights.

## 3. Data inputs and their intended use

| Input/source | Use | Boundary |
| --- | --- | --- |
| Admin title list | Define a batch; preserve spelling, year, language, notes | A title string is not a canonical identity |
| Admin-provided URL | Candidate source after allowlist and policy check | URL does not itself grant capture permission |
| TMDB API/local assets | Identity candidates, credits/character mappings and available metadata under current terms | API key does not imply paid-product rights |
| Wikidata | Cross-source IDs, multilingual labels, dates, credits, typed relations with references | One matching QID does not validate every field |
| Wikipedia/MediaWiki API | Revision-pinned, section-labeled plot, production, reception, themes, legacy | Respect endpoint policy, robots/rate limits; prose is not automatically a fact |
| SemEval and MF² | Isolated development/evaluation controls and diagnostics | Do not import benchmark labels, answers or false claims as catalog truth |
| Reviews and essays | Attributed critical perspectives where the specific use is allowed | Public visibility does not license copying, embedding or redistribution |
| Local IMDb datasets | Historical selection and identity-review aid within non-commercial terms | Not a product feed or current ranking authority |

Before enabling a source adapter, record allowed endpoints/purpose, rate
limits, robots rules, license scope, attribution, retention/redistribution
constraints and stop conditions. Access denial, 429, robots denial or unclear
rights means stop/quarantine, never bypass.

## 4. Catalog information contract

Unknown is explicit. Optional information may be absent; the report is
field-by-field and source-by-source, not a misleading overall “complete” score.

### Identity and release

- Canonical/original title, aliases, source language/script, work type and
  edition; keep remakes, films/series and alternate titles distinct.
- External IDs with their source assertion and matching decision.
- Release events with date, territory, event type and source. Festival,
  premiere and wide release need not collapse to one date.
- Identity state: `candidate`, `resolved`, `review_required`, `rejected`, or
  `merged_with_audited_reason`.

### Metadata and credits

- Runtime with edition/territory context where available; countries, languages,
  genres and production companies.
- Director, writers, producers, principal cast and available crew roles;
  preserve credited role, ordering, character name, source and disagreements.
- Actor-to-character pairing only when a source explicitly supports it. Never
  infer it from cast co-occurrence.

### Writer evidence

Keep attributable passages for plot, development/writing, casting,
production/design, cinematography/editing/music, reception, themes/analysis,
legacy/influence and awards/box office where source material supports them.
Keep the original section heading as well as its normalized category. A critic's
view stays attributed interpretation, not universal consensus. Full reviews
remain links/metadata unless specific text use is cleared.

Every passage carries snapshot ID, URL, revision/capture date, license,
attribution/access scope, original section locator, parser version, text hash
and offsets when recoverable. User-visible citations must resolve to retained
evidence.

## 5. Intake pipeline

### 5.1 Batch request and identity

An authenticated admin searches/selects multiple distinct films, disambiguates
by year/language/region/external ID, and submits a batch. An approved source URL
may be attached. Record input rows, submitting admin, policy version, requested
scope, idempotency key, state, attempts, errors and per-item outcomes. An email
address alone is not authentication.

Search the current catalog before creating anything. Rank identity candidates
using external-ID agreement, title/alias, release event, language, work type,
region and corroboration. Show reasons to a reviewer; candidate scores are not
proof. Conflicting IDs, same-title ambiguity, one-to-many results and year
mismatches require review. The 23 existing IMDb crosslinks have a recorded
pilot-membership disposition, but remain review-required for any operational
identity merge or field use.

### 5.2 Policy-gated capture

Only enabled source adapters may fetch. Retain original payload bytes and
response metadata locally, with hash, source URL, capture time, revision/ETag,
adapter version, policy version, attribution and license scope. Snapshots are
immutable; changed responses create new versions. Identical retries reuse the
snapshot. Rate-limit per source and persist checkpoints for safe resume.

### 5.3 Parse, normalize and validate

Use source-specific parsers for JSON/CSV/XML/HTML; regex only for bounded,
stable patterns. Preserve raw values and produce versioned normalized output.
Do not hand-edit individual film records. Validate snapshot hashes and
locators, external-ID uniqueness, title/year/language consistency, credit
shape, duplicate text, source attribution, permitted-use state, conflicts and
parser-version selection. Quarantine errors and malformed data visibly rather
than silently dropping or repairing them.

### 5.4 Review and publish

Automated checks produce a human queue for ambiguous identity, significant
conflicts, actor/character mappings, suspicious release events, rights
ambiguity and stratified passage samples. Record reviewer, decision, reason,
time and evidence. Machine `resolved` is not human review.

Preserve the project chain:

```text
immutable SourceSnapshot
  -> SourceAssertion / NarrativePassage
  -> reviewed operational Assertion (typed facts only)
```

Passages remain narrative evidence, not facts. Do not write to unused `Claim`
or `FilmRelationship` tables or add another live graph. Eligibility changes
must not erase the source capture.

### 5.5 Prepare and index evidence

Only integrity-valid, rights-eligible, selected-version passages are chunked.
Retain source/section context and citation IDs. Deduplicate identical text
without erasing revision provenance. Version chunker, model, index run and
input hashes; reuse vectors only when the complete input/model contract is
identical. Retry incrementally and surface failed records. PostgreSQL/pgvector
remains the baseline until measured data justifies a different service.

## 6. Observable batch states

Reuse existing job conventions where practical; do not add a generic job
framework solely for abstraction. The item lifecycle should express:

```text
submitted -> resolving -> awaiting_identity_review -> capturing -> parsing
          -> awaiting_quality_review -> publishable -> published -> indexed
          -> failed_retryable | blocked_by_policy | rejected
```

Persist per-stage timing, attempts, request counts, error category, checkpoint
and output IDs. Every batch report shows requested, unique, resolved,
review-required, captured, parsed, publishable, published, indexed, failed and
blocked counts. “1,000 requested” is never reported as “1,000 vetted.”

Per-batch local report includes input hash/version; identity decisions; field
and source coverage; rights/attribution/quarantine; passage counts by category
and revision; parser warnings and duplicate overlap; index/model/config and
timings; review sample and retrieval evaluation. Raw data, volumes, vectors,
models and large eval artifacts stay local/ignored. Git holds code, migrations,
docs and small fixtures.

## 7. Phased execution and exit gates

### Phase 0 — protect and reproduce baseline (partly done)

Keep the read-only readiness report, frozen pilot manifest, local identity
evidence audit and passage-version selector. Add deterministic manifest and
identity policy tests. Freeze current questions, evidence and latency outputs.

**Exit:** input hashes and counts reproduce; isolated tests pass; working corpus
has not been mutated.

### Phase 1 — settle identity and response contract

Pilot-membership dispositions for all 23 crosslinks are recorded separately
from the immutable candidate manifest; any unresolved or non-pilot identity
use stays flagged. Trace empty legacy release-date/runtime fields to their
sourced assertions/events and define an evidence-backed projection. Inspect
character assertions and API serialization; distinguish source-missing from
presentation failure. Specify batch API, source policy, review state and
report fields additively, reusing existing schema where possible.

**Exit:** all pilot identities have explicit states; release and credit UI
fields either show sourced values with attribution or exact missing status;
migration/API contract tests pass against isolated data.

### Phase 2 — one full vertical-slice ingestion

Use The Dark Knight as a richly documented case and one alternate-title case
for identity testing. Reuse retained authorized snapshots where possible; a
pasted URL is not permission to fetch. Demonstrate snapshot → parse →
validation/review → eligible assertion/passage → chunk → local vector → cited
response. Compare parser versions and prove deterministic/idempotent replay.

**Exit:** every displayed item traces to evidence, missing data stays explicit,
interruption resumes safely, and integration/UI checks pass without touching
the working corpus.

### Phase 3 — enrich and assess the 100

Process bounded, checkpointed batches through approved sources. Resolve all
identity/policy exceptions; inspect a stratified sample across source, parser,
language, era, remakes and credits; inspect every serious conflict. Compare
field/category coverage with baseline, reindex only changed eligible content,
and test frozen questions for relevance, citation support, attribution and
latency.

**Proposed gates, not current achievements:** every item has an explicit
identity state; no policy-blocked material is published; displayed release and
credit fields have source-aware states; at least 95 films have usable plot
evidence or an explicit source-unavailable explanation; no unresolved critical
defect in the reviewed extraction sample; both-film supporting evidence found
for at least 80% of cases judged supportable for both films. Report exact
denominators, per-pair results and failures. This small pilot does not establish
general product accuracy.

### Phase 4 — expand to the frozen 1,000

Freeze a deduplicated target manifest and selection provenance. Do not use
IMDb-derived product fields absent rights clearance; source product data from
eligible alternatives. Process bounded resumable batches, review exceptions,
sample by source/parser/language/year, and run frozen plus film-disjoint
questions. Report state counts and limitations, not a single completion %. Prove
backup/recovery and safe replay locally.

**Exit:** indexed material meets eligibility gates; no critical provenance or
answer-quality regression on held-out film pairs; unresolved records are
visible and excluded where appropriate; pipeline and recovery are repeatable.

### Phase 5 — routine intake and productization

After the 1,000 gate, build the authenticated admin batch UI, status/errors,
review actions, and separate user movie-request queue. Add Indian-language
editions through the same lifecycle, preserving scripts, aliases, local release
semantics and source language. Reassess scaling only against measured workload.

## 8. Writer-value evaluation

Keep separate: (1) eligible catalog evidence, (2) development questions and
source-span labels, and (3) frozen holdout pairs/questions unavailable to
tuning. SemEval/MF² remain external diagnostics, not product truth. Each
question's labels should identify which exact source spans support which
dimension: plot fact, action/choice, consequence, craft, attributed
interpretation or counterevidence. Mark support independently per film.

Measure evidence relevance at fixed context budget, both-film coverage, source
and section diversity, citation entailment, character attribution, question
coverage, useful contrast, abstention quality and p50/p95 latency. Separate
retrieval failure from generation failure. Accept a larger model/reranker only
if it improves the same frozen cases enough to justify memory, latency and
operational complexity. After technical gates, run blinded writer review of
whether the tool helped them notice, compare or develop something; benchmark
scores alone do not prove creative value or willingness to pay.

## 9. Test and policy constraints

- New tests use no mock/patch framework. Pure policies use retained fixtures;
  PostgreSQL/pgvector, migrations and API tests use `cinegraph_test` only.
- Never truncate or validate against working `cinegraph`. Normal tests do not
  fetch external sources; live contract checks are explicit, sequential and
  rate-limited manual actions.
- No arbitrary URL crawling, access-control bypass, automatic fuzzy merge,
  generated-fact promotion, second graph, second vector DB before evidence of
  need, or manual per-film record editing.
- Public visibility/non-commercial research access does not establish rights
  for a paid service. Before commercialization, assess current source terms,
  derivatives, attribution and storage/redistribution with appropriate legal
  advice.
- Keep raw sources, database volumes, embeddings, model weights and large
  artifacts local. Never commit keys or user-local `.agents/` / `.codex/`.

## 10. Immediate work queue

1. Make pilot manifest validation reproducible from hashes and test its
   77-exact / 23-review-required result.
2. Add compact, per-film output for character mapping and source-use
   eligibility; current aggregate counts are insufficient for review.
3. Trace why only 19/100 legacy profile dates and runtimes are populated while
   all 100 have release-event years; run
   `scripts/audit_pilot_metadata_projection.py` to compare each legacy value
   against eligible release events/runtime assertions before any backfill.
4. Audit the actor-character evidence and UI path to separate absent source
   data from API/display defects.
5. Complete one policy-approved, resumable ingestion vertical slice, then test
   on isolated data before any catalog write.
6. Only after those gates, process the 100, measure evidence gains, and run the
   frozen retrieval/generation evaluation.

**Immediate deliverable:** reproducible audit plus one end-to-end replayable
film intake and a visible delta report for new, unchanged, missing and
quarantined evidence. Not immediate: bulk-import benchmarks, claim 1,000-film
quality, deploy, or provision for 100,000 films.

## Appendix — state vocabulary

- `requested`: input batch contains the film.
- `candidate`: possible catalog identity found.
- `resolved`: selected under a stated policy; not necessarily human-reviewed.
- `review_required`: identity, content, rights or conflict needs decision.
- `captured`: source response retained with hash and policy metadata.
- `parsed`: versioned extraction produced records.
- `eligible`: integrity and allowed-use checks passed for the named use.
- `published`: available through the application projection.
- `indexed`: eligible passages have current index entries.
- `evidence-ready for question`: evidence supports this specific query and
  needed film(s); it is not a permanent completeness property of a film.

## Implementation checkpoint — 3 November 2026

- The pilot manifest now has a reproducible, offline validator. It checks the
  three input fingerprints, exact CSV row correspondence, identity-state
  shape and rank-specific IMDb-review evidence. The local result remains
  77 exact title/year candidates and 23 review-required crosslinks; none was
  approved or merged by this check.
- A read-only query of the same 100-film pilot through the rights-aware
  research read model returns 100/100 release years, 70/100 exact release
  dates and 82/100 runtimes from display-eligible metadata. This is better than
  the unfiltered projection's 0/100 runtime output, where restricted-source
  conflicts masked otherwise consistent open Wikidata values. It is still
  presence, not factual review.
- Research metadata, era signals and sourced-credit groups now use a shared
  source-rights policy. Default display accepts `open`, `attributed_reuse` and
  `attribution_required`; `local_noncommercial_only` needs the explicit local
  setting. `metadata_link_only` and `review_required` are excluded. API
  evidence now carries source name, license and rights status; the film page no
  longer falls back to an unsourced/legacy value when research metadata exists
  but has no eligible value.
- Actor-character values for the pilot were found in restricted IMDb/TMDb
  assertions, but no character-bearing cast mapping was in the prior
  rights-filtered set. The data currently shown by default therefore still
  lacks actor-to-character mapping; it needs an eligible source, not a UI
  guess. (Review this count again after the tighter source-state policy.)
- Verification so far: source-rights/metadata unit tests pass; the complete
  read-model PostgreSQL integration suite passes 13/13 against
  `cinegraph_test`; the repository integration gate passed 69 tests; frontend
  production build passed. A normal Conda collection initially lacked the
  pinned `mwparserfromhell` package; the project-local vendor fallback was
  used for offline unit collection. No working-corpus records were changed by
  tests.
- At this checkpoint, still pending: record dispositions for all 23 identities;
  audit which metadata conflicts are genuinely alternate release events
  versus bad old projections; source-eligible character credits; complete a
  source-policy-aware intake review; and run the frozen writer-question evaluation
  after enrichment. This checkpoint is not Phase 1 or Phase 3 completion.

### Follow-up implementation — preserve release-event scope

- Read-only inspection of *The Dark Knight Rises* showed that the legacy
  `Film.release_date` value `2022-10-06` is not its first release, but it is
  present as an exact, source-backed release event qualified to place `Q851`.
  The same eligible Wikidata revision records its 2012 release events. The
  earlier UI therefore mislabeled a valid later event as a date conflict by
  comparing years while discarding event qualifiers.
- The research metadata projection now retains all eligible dated release
  events, including year, exact date where known, place IDs, source/revision,
  rights and license metadata. The film page can inspect those events and
  distinguish a recorded later event from a date not supported by the current
  research sources. `release_date`/`release_year` remain the earliest recorded
  event, not a claim that every territory used that date.
- Added a pure policy test for a 2008 first release plus a 2022 event qualified
  to Q851; the isolated PostgreSQL/API fixture exercises the same distinction.
  Browser coverage now expands the film's event list and verifies the place
  link. This corrects presentation only; it does not rewrite a catalog row or
  endorse every Wikidata release assertion.
- Verification after the change: 238 backend unit tests passed (60 skipped),
  69 isolated PostgreSQL/API integration tests passed, all 7 Playwright flows
  passed using the installed Chrome, and the Next.js production build passed.
  The local working-catalog inspection used a read-only transaction; no
  working corpus rows were modified.
- Still pending for Phase 1: review all pilot release-date/event mappings
  rather than extrapolating from this example; determine whether eligible
  actor-to-character evidence is absent or only missing from the main profile;
  and audit source/parser selection before any batch ingestion.

### Follow-up — pilot crosslinks receive a selection-only disposition

- A deterministic, local adjudication command now binds the frozen top-100
  manifest, its IMDb title/year review, and the separately captured Wikidata
  P345 evidence by content hash. It fails closed unless each crosslink maps to
  exactly one catalog film/QID, has a unique title/year resolver candidate
  scoring at least 0.80, and has a resolved, attributed matching P345
  assertion.
- All 23 candidates meet that bar for **pilot list membership**. The weakest
  is `Sunset Blvd.` / `Sunset Boulevard` at 0.8148; the normalized abbreviation
  is recorded rather than represented as literal title equality. The other 22
  score at least 0.9.
- The frozen manifest is not edited. Each underlying `review_required`
  identity state remains so for any operational merge or field reuse. The
  local ignored report `catalog-pilot-identity-decisions-v1.json` records the
  limited scope and hashes; IMDb dataset fields remain non-commercial and are
  not authorized for product display.
- Three pure-policy tests cover positive, missing-P345 and weak/mismatched
  title-year evidence. Targeted suite: 11 passed. The command produced 23/23
  decisions without database reads or writes.
- Phase 1 remains incomplete: the 100-film release-date/runtime and
  source-eligible credit audits, plus the intake vertical slice, are still
  required before enrichment.

### Follow-up — release precision contract

- Research release events now retain source precision in the API. The film
  profile distinguishes year-, month- and day-precision values; unsupported
  sub-day values are not collapsed into a date by the display projection.
- Verification: 8 focused backend policy/response tests and the Next.js
  production build pass. API integration and browser assertions were added,
  but could not be executed because this session cannot connect to Docker.
  No working-corpus data was changed. This does not close the pilot-wide
  release-event audit.

### Follow-up — reproducible pilot metadata projection audit

- Added `scripts/audit_pilot_metadata_projection.py` and pure classifications
  for each legacy release date/runtime against the rights-filtered research
  read model. The report preserves event territory, exact source assertion
  values, source rights/license, and review state; it distinguishes a valid
  later-territory event from an earliest-event match, a year-only match, and a
  true year disagreement. Runtime outcomes separate projection omissions,
  conflicting/ambiguous eligible evidence, local-only evidence and no source
  value.
- The command enforces a 100-film/unique-ID manifest, local `cinegraph` DB,
  read-only transaction, local-only `data/evaluation` input/output and
  write-once report. It writes no corpus data and does not promote assertions.
- Verification: five focused pure audit tests and eight research-metadata
  tests pass (13 total); Python compilation and `git diff --check` pass.
  The report itself has not yet been generated: Docker/PostgreSQL is not
  reachable in this session. Therefore the 100-film statuses remain unknown,
  not inferred from aggregate counts.
