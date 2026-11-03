# CineGraph catalog preparation and expansion plan v1

Status: decision and execution plan, 3 November 2026. This document defines
how the newly audited datasets should and should not affect the catalog, and
the staged path from the current local corpus to a vetted 1,000-film reference
collection. It is not a claim that the catalog is complete, commercially
cleared, or writer-grade.

Related plans: [catalog and narrative data plan](catalog-and-narrative-data-plan-v1.md),
[catalog expansion execution plan](catalog-expansion-execution-plan-v1.md),
[open narrative datasets audit](open-narrative-datasets-audit-2026-11.md),
[RAG experiment program](rag-experiment-program-v2.md), and
[core architecture and test gates](core-architecture-and-test-gates-v1.md).

## Executive decision

Use the new narrative datasets first as **isolated evaluation material**, not
as bulk product data. Prepare the catalog from source-specific, attributable
records, beginning with a ten-film end-to-end slice, then the frozen first 100,
then the selected 1,000. Do not wait for 1,000 films to build or test the
pipeline; do not call a title "ready" just because it has a row, a Wikipedia
page, or an embedding.

The target writer flow is: a writer selects two films and asks a question in
their own words; CineGraph retrieves source passages relevant to that question
from each film, shows where each passage came from, and helps the writer
compare choices, pressures, consequences, and craft. Metadata supports
filtering and factual context. Passages support interpretation. A vector is a
replaceable retrieval aid, never a fact or source.

## 1. First-principles constraints

The irreducible inputs to a trustworthy comparison are (1) correct film
identity, (2) evidence that actually bears on the writer's question, (3) a
traceable source and permitted use for each displayed item, and (4) an answer
that does not claim more than that evidence supports. More titles, pages,
passages, model parameters, or vector rows cannot substitute for any of these.

Design consequences:

- Keep one source of truth for typed facts: immutable source snapshot →
  extracted source assertion → reviewed operational `Assertion`.
- Keep plot, criticism, essays and production prose as source-linked narrative
  evidence. They are not silently converted into facts or consensus.
- Keep source text, rights decisions, identity decisions, and model-derived
  indexes separately inspectable. Unknown and blocked are real states, not
  blanks that ingestion should guess through.
- Prefer the existing PostgreSQL/pgvector and source/job boundaries. Add a
  service, table or index only when a measured need cannot be served cleanly by
  the current design.
- Work locally for the current collection. Raw data, snapshots, full reports,
  model weights and vectors stay outside Git. Git receives code, migrations,
  documentation and small fixtures only.

## 2. What the newly audited data contributes

The 3 November audit confirmed two useful but different controls:

| Resource | What it can test | What it cannot make true |
| --- | --- | --- |
| SemEval-2026 narrative similarity | Whether methods notice human-annotated theme/action/outcome similarities across stories | Film identity, query-conditioned evidence retrieval, a canonical film fact, or useful writing advice |
| MF² | Claim/evidence diagnostics involving attribution, temporal/causal detail and text-only support limits | A general plot corpus, universal film understanding, or upstream rights to each underlying subtitle |
| Current film source snapshots/passages | Source-linked metadata and narrative evidence, subject to identity, rights and parser review | Completeness, commercial clearance, relevance to every question, or verified interpretation |

Use benchmark questions, answers, labels and false claims only in the isolated
evaluation area. Never inject them into production passages, assertions,
embeddings or prompts as if they were film evidence. The prepared benchmark run
contains 1,325 documents (1,219 distinct story summaries, 53 MF² transcripts,
53 synopses), but these are not 1,325 new films. SemEval includes non-film
stories; MF² and its subtitles require film-identity and asset-rights review
before any evidence reuse. The full details, overlap checks and exceptions are
in the dated audit and RAG plan linked above.

The benchmark advantage is earlier diagnosis: we can test whether narrative
similarity and source-grounded claim handling work before making the live
catalog larger. It does **not** solve our known catalog gaps in cast-to-role
mapping, dates, coverage depth or source eligibility. Catalog enrichment must
come from approved film-specific sources.

## 3. Catalog readiness snapshot and interpretation

The current local working catalog contains 2,586 film records. Existing audit
counts report 2,586 Wikidata IDs; 1,487 films with Wikipedia narrative
passages; 1,461 with plot-labelled passages; 1,278 with production passages;
1,345 with reception passages; 2,575 with a resolved director assertion;
2,491 with a resolved cast assertion; 267 with a resolved character assertion;
2,102 with resolved release-event assertions; and a 1,000-film embedding
collection using `qwen3-embedding:0.6b`. Counts are presence indicators, not
completeness, accuracy, licensing or quality scores.

Important audit cautions:

- Legacy `FilmCredit.character_name` is empty; newer character assertions are
  not proof that actor-to-character mappings are complete or correctly
  projected to the user interface.
- The older profile fields are sparse and may conflict with newer sourced
  research metadata. A date is a release event qualified by territory/type,
  not necessarily one globally unique premiere date.
- The 1,000 selected titles, 2,586 local catalog rows and 1,000 currently
  indexed films are different populations. Completion percentages must always
  name the frozen manifest and the exact denominator.
- The supplied IMDb CSV is a historical selection input. IMDb's local datasets
  are personal/non-commercial; they must not become a paid-product feed absent
  separately valid rights. A TMDB API key likewise is not a grant for every
  intended commercial use.

The current bottleneck is not just count. It is field-level evidence quality,
coverage that is uneven between films, source-use eligibility, identity
decisions, and the distance between ranked passages and a grounded answer.

## 4. Source plan: what enters which layer

Every adapter begins with a written source policy: permitted endpoint and
purpose, applicable terms/license, attribution, retention and redistribution
limits, robots/access rules, rate limit, request identity, retry/stop behavior,
and whether text may be stored, displayed, or embedded. Rights are decided per
source and asset/use—not inferred from public visibility or a dataset wrapper.

| Source | Near-term role | Admission rule |
| --- | --- | --- |
| User/admin title list | Defines the desired collection and preserves the submitted spelling/year/language | Treat as selection only; resolve identity before creating a catalog work |
| Local IMDb dump | Local title lookup and non-commercial selection/identity-review aid | Do not publish its fields or use it as a paid-product source without valid rights |
| TMDB API | Candidate IDs, metadata and cast/character candidates when available | Persist terms/policy version and attribution; only publish fields the applicable plan/use permits |
| Wikidata | External IDs, labels, release/credit candidates and typed relationships with references | Retain statement qualifiers/references; assess each property and source independently |
| English Wikipedia / MediaWiki | Revision-pinned plot, production, reception, themes and legacy passages | Use only permitted API/routes; preserve revision, attribution, license and source locator; never evade denial/robots/rate limits |
| Other approved open/local sources | Fill named gaps such as structured credits, releases or first-party production facts | Add a source only after actual dataset/API, terms, asset scope and adapter contract are verified |
| SemEval and MF² | Isolated retrieval/understanding evaluation | No operational catalog ingestion by default; any later exception requires independent identity and per-asset rights review |
| Reviews and essays | Attributed perspective and critical reception | Prefer links and bibliographic metadata; store/embed full text only when the specific text and use are cleared |

Open-web discovery is a research step, not permission to scrape. Unknown,
denied, robots-disallowed, rate-limited or unclear-rights assets stop or enter
quarantine. Never bypass access controls. For a 1,000-title run, use
source-specific sequential requests, bounded batches, checkpointing and
explicit resume; API calls must be budgeted and logged by source.

## 5. What one catalog film means

The catalog is a linked set of records, not one overfilled movie JSON object.

| Record group | Required behavior |
| --- | --- |
| Film/work identity | Canonical work, source labels/aliases, original-language title where known, work type, language, year, external identifiers, identity decision and evidence. Keep remakes, editions, series and same-title works distinct. |
| Release events | Date or year, event type, territory/place, source, revision and qualifier. Festival, premiere, theatrical territory release and streaming release may coexist. Preserve disagreements rather than choosing one date silently. |
| Credits | Person, credited role, ordering/billing when available, character name when explicitly sourced, source and review state. Do not infer who played whom from cast membership alone. Preserve source-specific credit variants. |
| Other metadata | Runtime with version/territory context where available; production companies, countries, original languages, genres, content/rating indicators where approved. Unknown stays unknown. |
| Narrative evidence | Original and normalized section/category, source document/revision, exact locator, text/hash, language, parser version, rights/attribution state and capture time. Categories may include plot, development/writing, casting, production, visual/audio craft, reception, themes/analysis, legacy, awards/box office. Only present categories are represented. |
| Relationships | Typed sequel/remake/adaptation/source-material relations only when supported by explicit reviewed evidence. Theme resemblance is a retrieval result or candidate, not a graph edge. |
| Derived retrieval artifacts | Versioned chunks/spans, embedding model/run, vector, index and eligibility decisions. Rebuildable from eligible passages; do not replace or obscure source evidence. |

Essays and criticism matter because they preserve attributed interpretations,
historical context and competing readings that basic metadata cannot provide.
They should be stored as perspectives with author, publication/date, URL,
rights and excerpt boundaries—not flattened into a single “film meaning.”
Until reuse is clear, keep a link and concise factual citation metadata rather
than copied full text or embeddings.

## 6. Repeatable ingestion lifecycle

```text
admin title/link selection
  → identity candidates and explicit resolution/review
  → source-policy check
  → immutable source snapshots
  → versioned parsers produce source assertions and narrative passages
  → validation, source rights and conflict checks
  → review queue / publish eligible records
  → field and evidence coverage report
  → eligible passage segmentation and chunking
  → incremental embedding/index run
  → fixed question evaluation and human spot review
```

### 6.1 Intake and identity resolution

1. Accept either a title plus optional year/language/region or a URL from a
   source-specific allowlist. A URL is a locator, never blanket crawl consent.
2. Search the local catalog and source indexes first. De-duplicate repeated
   entries within a batch and by stable source identifiers.
3. Rank candidates using exact external IDs first, then title/alias and original
   title, release-year/events, language, work type and corroborating evidence.
   Display match reasons and competing candidates to the operator.
4. Auto-resolve only deterministic unambiguous cases under a tested policy.
   Same-title collisions, remake/edition ambiguity, conflicting IDs and
   unsupported year mismatches go to `awaiting_identity_review`.
5. Preserve submitted values and all candidate decisions. A correction is
   additive/auditable; never rewrite the raw input or merge identities because
   a similarity score is high.

### 6.2 Source capture and extraction

1. Fetch only through enabled adapters after policy validation. Store response
   bytes and headers/metadata locally with URL, retrieval time, source revision
   or ETag, hash, size, adapter/policy version, language, license and
   attribution. Snapshots are immutable; updates create new snapshots.
2. Reuse byte-identical snapshots and successful stage outputs on retries.
   Checkpoint by film/source/stage so a stopped batch resumes without
   recrawling completed work.
3. Parse structured formats with their parsers; use regular expressions only
   for stable bounded patterns. Preserve raw source values alongside
   normalized values. All transformations are scripted and versioned, not
   hand-edited per film.
4. Extract narrative sections without merging them into one opaque synopsis.
   Preserve nested section heading, locator, revision, citation metadata and
   parser warnings. Compare changed parser output at section/text level before
   replacing a selected extraction version.
5. Source assertions are replayable interpretations of snapshots. Facts enter
   the existing `Assertion` projection only after eligibility and review
   policy. Narrative prose remains a passage. No writes to `Claim` or
   `FilmRelationship` as a second live fact store.

### 6.3 Validation and review

Automated gates produce a report and quarantine item-level exceptions rather
than silently dropping or guessing:

- snapshot hash, source identity, revision/locator and attribution present;
- external IDs are correctly shaped and not ambiguously attached to two
  active films;
- title/year/language/type agree or a conflict is visible;
- each normalized field retains source and rights status;
- release-event place/type qualifiers survive parsing;
- credits preserve role and ordering; character mapping has direct source
  evidence; disagreements remain inspectable;
- parser output has no empty, duplicated, malformed or unexplained dropped
  sections; source quote locators resolve to exact retained content;
- passages and embeddings are eligible for their intended use under policy;
- chosen extraction/chunk version is singular and explicitly selected.

Human review is reserved for high-impact ambiguity and meaning: identity
exceptions, rights exceptions, actor/character mappings, conflicting important
metadata, parser changes and a stratified sample of narrative sections. Store
reviewer, timestamp, decision, reason and evidence reference. A database state
named `resolved` is not equivalent to human factual review.

### 6.4 Index preparation

Create chunks only from selected, integrity-valid, use-eligible passages.
Preserve source title/section context and exact offsets; do not pad with
unrelated sections to meet a target token count. Record chunker/version and
model digest. Reuse a vector only if passage hash, segmentation, model
revision, prompt/prefix and normalization contract all match. Indexing is
incremental and resumable. Rebuild a versioned index rather than rewriting
source text when a model changes.

At query time, use the writer's actual prompt, selected film IDs and permitted
evidence filters. Return ranked evidence by each film and section, provide
source citations and let the user inspect/pin passages. Generation may only
work from the retrieved bounded evidence and must abstain or describe missing
support. Retrieval quality, citation support and writer usefulness are
separate evaluations.

## 7. Visible stages and operator workflow

The current local operator intake already supports an authenticated bearer
token, title suggestions from a local IMDb index, multi-select up to 20 films,
job submission, progress listing and a source/passages preview. It is a useful
shell, not yet a complete multi-source catalog curation system. The local
operator key is not user authentication and an email string is not a secure
admin role; production must use real authentication and server-side
authorization for the configured admin identity.

Recommended job states:

```text
queued → resolving_identity → awaiting_identity_review → policy_check
  → capturing → parsing → validating → awaiting_quality_review
  → publishable → published → indexing → indexed
  ↘ failed_retryable | blocked_by_policy | rejected
```

Each film/source stage records attempt, start/end/duration, request count,
checkpoint, error class, output IDs and retryability. The UI should show counts
by stage, per-film failures, source policy blocks, missing fields, duplicate
matches and review actions. It should never show one green “success” where
facts are published but the plot failed or rights block indexing.

Admin can later attach an allowlisted source URL or corrected identity as an
input to the same pipeline. This creates a reviewable candidate, not an
immediate fact. Public user movie requests should be a separate queue with
deduplication and moderation; user requests must never trigger arbitrary
network fetching.

## 8. Evaluation plan and go/no-go gates

### Gate 0 — freeze and report the baseline

- Freeze the target manifest and all input hashes; record whether each row is
  requested, matched, unresolved or duplicated.
- Produce per-film source/field coverage and rights-state counts before any
  write batch. Report current 2,586 catalog separately from the target set.
- Snapshot current endpoint, retrieval and latency behavior for comparison.

**Pass:** reports reproduce exactly from their inputs; no live catalog mutation.

### Gate 1 — 10-film pipeline vertical slice

Select ten films that exercise common and hard cases: different eras, remakes
or same-title ambiguity, a non-English original title, varying Wikipedia
article depth, differing release events, cast-character mappings and at least
one pair used in writer questions. Resolve every identity and process all
configured sources end to end. Keep a per-film exception report.

**Pass:** every displayed fact has provenance; every passage has a valid
snapshot and source locator; source restrictions are applied; retries are
idempotent; parser and identity exceptions are visible; no inferred cast-role
claims; admin can inspect status/preview. Do not require every film to have
every kind of evidence.

### Gate 2 — first 100 quality pilot

Run the frozen first-100 manifest, retaining the exact source-selection input
as local audit material. Review the 23 current ID crosslinks explicitly; do
not silently accept or merge them. For each row calculate counts and status
for identity, release events, core metadata, director/writer/cast, explicit
character mapping, plot, production/craft, reception/theme/legacy, rights,
passage eligibility and indexing. Stratify human review across source types,
languages, title-match types, sparse/rich pages and parser warnings.

**Pass:** all 100 have a documented selection-to-catalog mapping and explicit
identity state. The 23 crosslink decisions are pilot-membership-only; any
operational identity merge or product field reuse requires its own evidence and
review. No source is published outside its allowed use; source/field coverage
is reproducible;
sampled facts and passages match the retained source; missing values are
honestly shown. Track eligible, blocked and review-needed counts separately.

### Gate 3 — question-conditioned retrieval

Create a frozen set of ten film pairs and five natural writer questions per
pair. Include questions about conflict/loyalty, goal/opposition, choices and
consequences, family/justice, character change, visual/audio craft, production
choices and contrasting interpretations. Do not hard-code a small menu of
answer templates; the user's question must condition retrieval. Label per film
which evidence is relevant, partially relevant, insufficient or contradicted.

Run the unchanged baseline and candidate policies on identical data. Score
retrieval (both-film relevant evidence, rank/coverage, missing evidence), then
generation (claim support, character attribution, coverage of the prompt,
useful contrast, calibrated abstention), then writer usefulness. Report
denominators and per-pair outcomes. Benchmark scores from SemEval/MF² remain
separate. The proposed 80% both-film evidence target applies only to cases
independently judged supportable for both films; it is a gate to investigate,
not an accuracy claim.

**Pass:** no critical unsupported claim or character misattribution in the
reviewed release set; material retrieval improvement over baseline; acceptable
local latency and memory; a writer reviewer finds the output useful on a
predeclared sample. If not, identify data, retrieval, generation and UX causes
separately before choosing a fix.

### Gate 4 — expand from 100 to the selected 1,000

Only after Gates 1–3, process bounded resumable batches. Do not re-fetch or
re-embed unchanged eligible content. Track the whole batch from input row to
published film and indexed passage. Run a fresh stratified sample and retain
all error/quarantine counts. Re-run the frozen evaluation unchanged; add new
film-disjoint questions for expansion without tuning the original holdout.

**Pass:** a versioned 1,000-title manifest and run report establish the exact
number resolved, evidence-ready, published, indexed, review-required,
rights-blocked and failed. “1,000 requested” is not “1,000 ready.”

### Gate 5 — routine future intake

Use the same source-policy, identity, capture, parse, validate, review and
index interfaces for later English and Indian-language additions. Language is
per record and passage; source scripts and original titles are preserved.
Introduce an adapter/configuration for each additional language rather than
hard-wiring English extraction assumptions. Reassess database or vector
infrastructure only from measured search/index/operational bottlenecks.

## 9. Required report for every batch

Write a local versioned report (not a Git data dump) containing:

- input manifest, source list/policy versions and SHA-256 fingerprints;
- requested, unique, existing, candidate, resolved, review, rejected counts;
- per-film source snapshots, revision/date, hash, license/rights and
  attribution state;
- field-by-source coverage, conflicts and missing-value counts;
- credited roles and explicit character-map coverage;
- narrative passage counts by source, section, parser and eligibility state;
- duplicate/overlap, parse warnings and quarantine reasons;
- chunk/index/model versions, reused/new/skipped/failed vector counts and
  durations;
- job timings, request counts, retries, rate-limit events and errors;
- review sampling frame, decisions and cited snapshots;
- fixed retrieval/generation results, latency and separate error categories.

The report must retain exact denominators, not combine unlike measures into a
single quality percentage. Store large raw inputs, full passage exports,
vectors, model artifacts and generated eval runs locally; Git contains a small
schema/fixture only when needed for deterministic tests.

## 10. Non-goals and explicit risks

- No general web crawler, arbitrary-URL importer or robot-rule bypass.
- No use of benchmark answer/fib labels as corpus truth; no claim that the new
  datasets increase film coverage.
- No immediate 100,000-film provisioning, extra graph database or separate
  vector service. Local PostgreSQL/pgvector remains until benchmarks show a
  real limit.
- No false completeness promise: a film may lack reliable craft or critical
  evidence even after all allowed sources have been checked.
- No commercial-readiness claim until each data source and derivative's
  intended commercial rights, attribution and retention are reviewed.
- No automatic promotion from a model's inferred theme or relation into a
  canonical fact.

Main risks are (a) source terms not allowing the intended storage/display/use,
(b) ambiguous film identity, (c) inconsistent coverage, (d) Wikipedia article
structure changing, (e) actor/character attribution errors, (f) apparent
retrieval quality inflated by duplicates or benchmark leakage, and (g) local
disk/memory/latency limitations. The gates above are designed to surface each
before it is scaled.

## 11. Immediate sequence

1. Keep the newly prepared SemEval/MF² artifacts isolated; use them to validate
   benchmark preparation and future retrieval/generation diagnostics only.
2. Complete the already-started Phase 1 audit: verify all 100 frozen
   selection-to-catalog mappings (the 23 crosslinks now have a
   pilot-membership-only disposition), reconcile legacy dates/runtime, and
   audit eligible actor-to-character assertions against what the API/UI
   actually displays.
3. Produce a read-only gap list for the frozen ten-film slice and 100-film
   pilot, including explicit source/rights policy and missing fields.
4. Exercise the admin intake vertical slice in the isolated test stack; fix
   idempotency, stage visibility, review and preview before production writes.
5. Process the ten-film vertical slice under approved policies; inspect every
   source-to-UI path and report exceptions.
6. Proceed to the 100-film pilot only after Gate 1; proceed to the 1,000 only
   after pilot quality and question-conditioned evaluation pass.

No completion percentage or delivery date is estimated here. Each phase has a
verifiable artifact and an explicit go/no-go condition; the next report should
show counts and actual test results rather than activity or token volume.
