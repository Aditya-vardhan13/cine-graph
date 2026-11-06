# CineGraph catalog and evidence roadmap v2

Status: proposed execution baseline, 5 November 2026. This document consolidates
the next data/catalog milestones; it is a plan, not a claim that the corpus is
commercially cleared, writer-grade, or ready for expansion. The detailed source
and execution references remain the [catalog preparation plan](catalog-preparation-and-expansion-plan-v1.md),
[catalog execution plan](catalog-expansion-execution-plan-v1.md),
[narrative datasets audit](open-narrative-datasets-audit-2026-11.md),
[retrieval experiment program](rag-experiment-program-v2.md), and
[architecture/test gates](core-architecture-and-test-gates-v1.md).

## Decision in one paragraph

Do not solve weak answers by importing every available text or by increasing
the embedding model first. CineGraph needs (1) reliable film identity, (2)
source-specific, rights-aware evidence with useful section/role attribution,
(3) a retrieval evaluation that asks real writer questions, and (4) a
question-conditioned answer assembled only from evidence. The first
reproducible, resumable ten-film capture and extraction-integrity check has now
passed in isolation. The current milestone is to validate citation/reference
support and rights handling, then run question-conditioned retrieval on eligible
evidence. Do not start the 100-film expansion until those gates pass; expand to
the frozen 1,000 only after coverage, provenance and answer-quality gates pass.
No work on a 100,000-film system is needed now; every durable artifact and
adapter should be additive so more titles, sources and languages do not require
rewriting the pipeline.

## First-principles framing

### Assumptions to reject

- A larger dataset or vector count automatically improves answers.
- A Wikipedia page, API response, dataset licence, or public URL authorizes
  every storage, embedding, display, and commercial use.
- A cast list proves which performer played which character.
- One release year or date describes every territory and release event.
- A high semantic-similarity score proves that passages answer the user's
  particular question.
- A theme category, benchmark label, essay interpretation, or model-generated
  relation is a verified fact.

### What must be true for a useful answer

For a two-film question, the system must identify the intended works, retrieve
relevant evidence for each film, preserve who/what/when/where and source
context, distinguish source statements from interpretation, and abstain when
evidence is insufficient. The answer should compare concrete dramatic actions,
choices, pressures and consequences—not just matching labels. Therefore, the
quality unit is not “film row” or “embedding”; it is a cited answer to a
question with evidence coverage on both sides.

The practical floor is the least amount of permitted evidence and computation
that reliably supports the question class. Metadata is cheap and broad; deep
plot, production, reception, and criticism are uneven and source-constrained.
Keep those coverage dimensions separate rather than manufacturing a universal
completeness score.

## Current baseline and what new datasets are for

The latest audited local baseline is recorded in the [catalog and narrative
plan](catalog-and-narrative-data-plan-v1.md): 2,586 local film records, 1,487
with Wikipedia narrative passages, 267 with at least one character assertion,
and 1,000 represented by the existing `qwen3-embedding:0.6b` index. These are
presence indicators, not correctness, rights clearance, retrieval quality, or
complete actor-to-character coverage. The 100-film audit also found empty or
stale legacy release/runtime projections and significant character-credit
gaps. Do not infer the catalog is ready from the overall record count.

The isolated ten-film capture provides a second, source-snapshot baseline:
Wikidata has value-bearing statements for release date, runtime, director and
cast on all ten films; 214 of 328 cast statements include a character entity or
name qualifier, and 114 do not. The article capture yields 484 replay-verified
passages, but citation linkage is not support verification, rights clearance or
retrieval quality. These snapshot figures must not be conflated with the
working catalog or its public API. The isolated API/UI contract exercises one
actor-to-character credit and verifies that the credit statement, actor label
and character label link to separate provenance. This is fixture-level
contract coverage; projection and per-credit review of the retained ten-film
capture have not yet been completed. See the [ten-film coverage follow-up](catalog-and-narrative-data-plan-v1.md#follow-up--ten-film-structured-field-coverage-and-dataset-admission-plan-5-november-2026)
and [credit provenance follow-up](catalog-and-narrative-data-plan-v1.md#follow-up--credit-provenance-is-visible-and-tested-end-to-end).

The article-intake read path had also been selecting historical extraction v1
while the current parser emitted v6, which could make newly captured passages
look absent to the worker/API. This is corrected with explicit extraction
precedence and a v7 stored-passage derivative carrying citation coordinates;
the versioned chunker persists source-relative citation positions. This fixes
provenance loss and passage visibility, not semantic support or retrieval
quality; those remain gated and are tracked in the [implementation log](catalog-and-narrative-data-plan-v1.md#follow-up--extraction-version-gate-corrected-and-citation-positions-persisted-5-november-2026).

Recently audited narrative datasets have a bounded role:

| Resource | Use now | Do not do |
| --- | --- | --- |
| SemEval-2026 narrative similarity | Isolated development/control data for story-level theme, action and outcome similarity; inspect source-work overlap | Do not import its stories/labels as product facts or tune on the frozen test subset |
| MF² | Isolated diagnostics for evidence retrieval, attribution, temporal/causal claims and abstention; mark visual-dependent questions | Do not put fact/fib claims or false claims into film evidence; do not assume subtitle rights from the benchmark licence |
| MovieSum and other restricted collections | Research/schema reference only unless each asset and use is cleared | Do not treat non-commercial/research-only terms as commercial product rights |
| IMDb local datasets | Candidate selection and identity review under applicable limits | Do not publish/use restricted fields in a paid product absent a valid grant |

These resources can reveal failure modes and help compare methods. They do not
replace a rights-cleared, source-attributed product evidence pipeline or
question-conditioned writer evaluation.

## Target record model and evidence contract

Treat the catalog as linked records with source/version context, not a single
denormalized movie blob. Reuse the existing schema and source-of-truth chain;
add fields/tables only when an observed gap cannot be represented safely.

| Entity / layer | Required information | What it is not |
| --- | --- | --- |
| Film/work identity | Canonical work, work type, original title/script, aliases, language, year, external identifiers, identity decision and evidence | A title string or a fuzzy match is not identity proof |
| Release event | Date/year precision, event kind, territory, edition/context, source and qualifiers | One field called `release_date` that silently selects among events |
| Person and credit | Person identity, credited role, ordering/billing if available, character name only when sourced, snapshot/assertion and review status | Co-occurrence is not actor-character evidence |
| Metadata assertion | Raw source value, normalized value, source locator, confidence/state, qualifiers and reviewer disposition | Majority vote or silent overwrite across sources |
| Source snapshot | Exact response bytes, URL, retrieval time, source revision/ETag where available, hash, adapter/policy version, language, attribution and licence/use scope | A current response is not recovery of missing historical bytes |
| Narrative passage | Exact source text, section path/category, source snapshot/revision, language, locator/offsets when possible, extraction version and rights state | A canonical fact, universal interpretation, or independent evidence merely because it is embedded |
| Derived retrieval artifact | Chunk boundaries, input hash, chunker/model/index version, run/status and passage references | A new fact source or permanent truth |
| Critical/review perspective | Author/publication/date, URL, quoted/excerpt boundaries if eligible, viewpoint and source terms | “What the film means” as an unqualified single answer |

Preserve this chain:

```text
immutable SourceSnapshot
  -> replayable SourceAssertion and/or NarrativePassage
  -> reviewed operational Assertion for typed facts only
  -> eligible passage spans/chunks -> versioned embedding/index
  -> retrieved evidence -> attributed, question-specific answer
```

Narrative passages never become typed facts automatically. Semantic
relationships can be ranked as candidate evidence, but they never become
`Assertion` edges without explicit, reviewed, typed support. Do not create a
second live graph/fact store or write to unused `Claim` or `FilmRelationship`
tables.

## Source strategy: broad coverage without source conflation

Enable a source adapter only after recording its actual contract: allowed
endpoint and purpose, current terms/licence, attribution, retention and
redistribution, storage/embedding/display scope, robots rules, rate limits,
identification, stop behavior, parser version and raw-response strategy.
Public accessibility is not permission. Denial, robots exclusion, rate limit,
or unresolved use rights means stop or quarantine—not route substitution or
bypass.

| Source | Best near-term contribution | Main gate |
| --- | --- | --- |
| Admin-provided title list | Establish which films to prioritize; retain exact submitted text/year/language | Must resolve to a work before ingestion |
| TMDB API / local permitted data | Candidate identity, common metadata, cast and character candidates | Confirm current terms, attribution and product/commercial use per plan; API key is not a licence |
| Wikidata EntityData | External IDs, labels, dates, credits/relations with statement references | Known-QID route only under current robots policy; retain raw bytes/revision and property-level provenance |
| English Wikipedia article HTML | Deep, sectioned plot, production, reception, analysis and legacy context when article contains it | Capture only approved routes; exact revision, CC BY-SA attribution, source links, parser and text provenance; article depth varies |
| First-party studio/filmmaker/festival sources | Intent, production decisions, official credits/releases | Avoid treating promotional claims as independent criticism; record source and terms |
| Reviews/essays (e.g., publications and Letterboxd) | Attributed audience/critic interpretation and reception diversity | Default to link + bibliographic metadata; full-text storage, embedding, display or scraping only when the specific permission/access terms allow it |
| Benchmarks | Evaluate narrow capabilities and detect errors | Physical/logical separation from product corpus; split and rights audit |

No source is expected to fill every field. Prefer independent corroboration for
high-impact/conflicting metadata; record disagreements and scope. Keep an
explicit `unknown`, `not found`, `conflicted`, `not permitted`, or
`not reviewed` state rather than filling gaps with inference.

## Pipeline to build and operate

```text
Admin title batch
  -> local catalog/ID lookup
  -> candidate list + explicit identity decision
  -> source-policy gate per source/asset
  -> one-at-a-time immutable capture with checkpoint
  -> versioned parse and normalization
  -> validation, deduplication and conflict/rights quarantine
  -> review queue for ambiguous/high-impact items
  -> eligible assertions/passages
  -> film/category/source coverage report
  -> versioned chunks and incremental embedding
  -> paired-film, question-conditioned retrieval
  -> cited answer and writer usefulness evaluation
```

### Operational behavior

- Each batch and item has stable idempotency identity, requested work, source
  policy version, current stage, attempt count, checkpoint, error class and
  output identifiers. A restart resumes completed stages and does not refetch
  successful immutable captures unnecessarily.
- Keep raw captures and large derivatives local and ignored. Git contains code,
  migrations, documentation and small attributed test fixtures only.
- Parse source-native formats with real parsers; use scripted regex only for
  bounded stable text patterns. Preserve original values; version normalization
  and extraction. Do not manually patch film records one at a time.
- Process one source request at a time unless source terms explicitly permit
  more. Enforce response-size bounds, pacing, same-host redirect rules, and
  fail-closed behavior in the adapter; persist each successful capture before
  beginning the next item.
- Separate source-missing from parser failure, rights exclusion, identity
  uncertainty, operational projection failure and UI display failure.
- Build/index only allowed passages from the explicitly selected extraction
  version. Keep retrieval failures and partial evidence visible. Recompute
  vectors only when eligible source text or model/chunker contract changes.

## Phased execution, outcomes and go/no-go gates

### Phase 0 — protect the baseline and freeze inputs

**Work:** freeze title-list source/version/hash, current per-film coverage,
existing retrieval set, evaluation questions/labels, latency and worktree/data
boundary. Keep the working catalog read-only during the pilot.

**Visible outcome:** a reproducible manifest plus before-state report showing
film identity and field/category/source/index status separately.

**Gate:** no input ambiguity is hidden; report counts reproduce; integration
uses only `cinegraph_test`; normal tests do no external crawling and introduce
no mock framework.

### Phase 1 — one-film capture/parsing source contract

**Work:** use *The Dark Knight* as a parser/capture canary, not as a quality
claim. Verify identity, known Wikidata QID/sitelink, robots-checked source
policy, exact snapshot hash/revision, parsed section paths, parser-selected
version, attribution and rights state. Retain parser warnings and source
references. Do not mutate the working corpus.

**Visible outcome:** local audit report with snapshot → parsed assertion and
passage rows, section distribution, raw-versus-extracted checks, provenance,
and explicit exclusions. Small fixture and deterministic tests in Git.

**Gate:** byte integrity and repeatable parser output; redirects obey route
policy; unknown rights remain excluded; experimental parser versions cannot
leak into current-passage reads; relevant unit and isolated integration tests
pass.

### Phase 2 — ten-film isolated vertical slice

**Work:** process the frozen ten-film selection below through all enabled
sources one item at a time. Before fetch, verify each identity and exact
permitted article locator; no title-search fallback to disallowed endpoints.
Capture per-film checkpoint. Audit field/section coverage and each conflict;
do not publish the pilot to the working database.

Initial selection from the frozen title source:

1. *The Shawshank Redemption* (1994)
2. *The Godfather* (1972)
3. *The Dark Knight* (2008)
4. *The Godfather Part II* (1974)
5. *12 Angry Men* (1957)
6. *The Lord of the Rings: The Return of the King* (2003)
7. *Pulp Fiction* (1994)
8. *Schindler's List* (1993)
9. *Inception* (2010)
10. *Fight Club* (1999)

**Visible outcome:** local per-title coverage matrix; capture/error/resume
report; section and credit audit; sampled raw passage review; retrieval on a
frozen set of writer questions; no raw dataset or large report committed.

**Gate:** all ten have explicit identity states; every used output resolves to
an immutable snapshot, license/access decision and locator; no blocked or
unclear-rights data is indexed; job resumes safely after an induced ordinary
failure; duplicate content/revisions are reported; every retrieval answer has
evidence per film or explicit abstention; users can tell what is unknown.
If any source cannot legally/technically supply a field, mark it—not bypass.

### Phase 3 — frozen first 100 quality pilot

**Work:** only after Phase 2 passes, enrich 100 with the same pipeline. Resolve
the existing identity crosslinks for pilot membership separately from any
operational merge. Inspect all serious conflicts and a stratified sample by
source, era, language, article depth and credit type. Audit display/API
projection for dates, runtimes and character roles. Re-index only changed,
eligible text.

**Visible outcome:** per-field coverage change from Phase 0, evidence-eligibility
and review counts, retrieval report with per-query citations/errors, and
latency/memory cost for the current embedding baseline versus any challenger.

**Proposed gate (to freeze before looking at final results):** every title has
an explicit identity disposition; all displayed high-impact fields cite a
source and scope; no rights/robots violation; missing data is truthful and
visible; at least 95 of 100 have usable plot evidence or an explicit
source-unavailable state; paired retrieval succeeds on both sides in at least
80% of pre-judged supportable cases; all critical wrong-film, wrong-character,
unsupported-claim and broken-citation errors are reviewed. Report denominator,
query-level outcomes and abstentions; do not present this small sample as
general accuracy.

### Phase 4 — frozen 1,000-film reference collection

**Work:** freeze and hash the exact deduplicated target manifest; verify
selection rights/use. Run bounded checkpointed batches through approved source
adapters. Review all identity/policy/conflict exceptions and a stratified
quality sample. Use streaming or per-record persistence so a failure never
loses a batch of responses. Only derive/index content that passed its source
and eligibility gates.

**Visible outcome:** catalog coverage dashboard by film/source/field/category;
item-state counts for submitted, resolved, captured, parsed, review-needed,
eligible, published, indexed and retrieval-tested; retry/quarantine report;
storage, request, throughput, latency and resource costs; held-out quality
report.

**Gate:** reproducible manifest and pipeline; recovery/replay verified;
no unresolved critical provenance or rights issue in published evidence;
quality does not regress versus the 100 gate; unresolved titles remain
explicit and excluded where required. Completion is multiple state-specific
counts, not one percent.

### Phase 5 — product expansion, languages and sources

Only after the 1,000 reference gate, add sources/languages by configuration,
policy and source adapter. Start each language with its own identity, script,
normalization, aliases and field coverage audit; never silently mix translated
or dubbed text with the original evidence. Expand toward 100,000 only when
measured workload justifies storage/index changes; PostgreSQL/pgvector remains
the current baseline until benchmarked evidence demonstrates a better cost,
latency and operational tradeoff.

## Retrieval and answer evaluation contract

For every frozen case record: two canonical film IDs; exact writer question;
expected sub-aspects; supportability per film; relevant evidence IDs and
section/source; hard negatives/near matches; acceptable abstention; and
reviewer rationale. Keep questions, gold labels and benchmark text out of
production evidence. Split by film pair and, where relevant, source-work to
reduce leakage.

Measure separately:

| Failure surface | Evidence to inspect |
| --- | --- |
| Identity | Wrong edition/remake/language or film leakage |
| Retrieval | Relevant passage recall per film; top-k precision and rank; lexical/dense contribution |
| Evidence coverage | Which question aspects have support on each side; missing evidence vs retrieval miss |
| Attribution | Correct source, section, speaker/character and scope |
| Grounding | Each generated factual statement supported by cited passages; no invented details |
| Comparison | Concrete commonality and meaningful difference, not only broad theme overlap |
| Abstention | Does the response say evidence is insufficient when support is absent? |
| Writer utility | Does it provide an actionable craft question/move without prescribing the user's story? |
| Cost/performance | p50/p95 retrieval and answer latency, memory, token/context use, model/index cost |

Evaluate retrieval separately from generation. Compare embedding/reranker or
generator models with identical evidence, prompts, budgets, quantization and
questions. Larger models are adopted only for measured net improvement at
acceptable local latency/memory and, later, hosting cost. Valid JSON or
citation-shaped output is not evidence of correctness.

## Immediate next actions

### Verified status — 5 November 2026

Phase 2 has completed its first, deliberately narrow source-capture and
extraction check. This is not yet the full Phase 2 gate described above. The
following earlier v2 counts are historical; the current extraction baseline
is recorded in the v6 follow-up below.

- The frozen ten-title manifest resolved to ten unique QIDs; the available
  Wikidata identity assertions and English Wikipedia sitelinks passed the
  capture-time title/year/type checks.
- The local, resumable run captured ten article responses sequentially and
  retained exact bytes plus revision/URL/hash metadata outside Git.
- The versioned parser produced 496 sectioned passages across the ten films.
  All ten contain plot and production/casting sections. There were no exact
  duplicate passage texts; 426/496 passages (85.9%) contain citation markers.
  Two passages exceed 2,500 characters and should be reviewed for useful
  chunk boundaries rather than truncated blindly.
- The offline integrity audit passed 10/10 source records and replayed parser
  output from the retained source bytes. Its report contains counts and
  integrity results, not article prose.
- The citation audit exposed a parser v1 false positive: 28 page-number
  superscripts on *Inception* were mistaken for footnote markers. Parser v2
  accepts only actual article citation-marker IDs. The original v1 derivatives
  remain intact; v2 writes content-addressed derivatives with a separate
  manifest and audit. The corrected run still produces 496 passages; all
  2,610 citation-marker occurrences map to reference-list entries, and 1,655
  (63.4%) have at least one external URL. The other 955 include valid
  print/bibliographic references without external links. Only 155 of 426 cited
  passages have every marker linked to an external URL. These are locator
  metrics—not broken-reference, entailment, quality, or rights-clearance
  scores. The passage-level URL map remains local.
- Rights note: CC BY-SA 4.0 permits commercial sharing/adaptation subject to
  attribution, change notice, ShareAlike, and no-additional-restrictions terms
  ([license deed](https://creativecommons.org/licenses/by-sa/4.0/deed.en)). It is
  not equivalent to public domain. The legal treatment of CineGraph's chunking,
  embeddings, and generated comparison output is unresolved here; public
  monetization still needs counsel. Linked reference URLs have their own terms
  and are not cleared for ingestion by the Wikipedia article license.
- The WDQS `/sparql` clients now fail closed. Local admin intake uses a
  robots-checked article title or optional validated single-film article URL,
  then requires QID, film type, title/alias, release year and IMDb ID to agree
  before profile creation. Existing source bytes are stored only after
  identity validation and are not refetched for a second extraction pass.
- The focused source-capture/parser/citation suite passed 23 tests; the full
  non-integration suite passed 270; the isolated API/PostgreSQL suite passed 81 tests (270
  deselected; two third-party warnings). A production frontend build passed.
- A fresh shell live-probe could not resolve Wikimedia DNS, so the new combined
  title-derived intake path still needs a manual live source-contract check.
- The capture did not change the working catalog, generate embeddings, run
  paired-question retrieval, verify that references support each passage, or
  establish licensing/commercial eligibility. Therefore it does not pass the
  Phase 2 publication or retrieval-quality gate and does not authorize the
  100-film expansion yet.

### Current ten-film extraction and citation-locator result (5 November 2026)

- Parser v6 excludes bibliography/source sections and image-caption citation
  artifacts, and retains each marker's paragraph index and character offset.
  The v6 integrity replay passes **10/10** article snapshots and extracts
  **484 passages**. The earlier v2 total of 496 included 12 passages from
  bibliography/source content and is no longer the current baseline.
- The citation audit maps **2,612/2,612** marker occurrences to an article
  reference-list entry; **1,656 (63.4%)** resolve to at least one outbound
  URL. **956** have no external URL in the parsed reference entry (including
  potentially valid print/bibliographic references); 155/426 cited passages
  have every marker URL-linked. These are locators, not entailment, quality,
  or rights-clearance metrics. The per-passage evidence map is local/ignored.
- Regression and integration gates pass: 15 focused tests, 284 non-integration
  tests (50 skipped), and 81 isolated API/PostgreSQL tests (270 deselected) on
  `cinegraph_test`. No data was ingested into the working corpus, and no
  embeddings or retrieval run were produced.
- The first deterministic passage-boundary review selected 30 passages across
  plot, production and contextual sections; all 30 matched complete paragraphs
  under the expected full heading path in the retained HTML. This is a bounded
  structural sample, not source support review or corpus-wide parser approval.
  The prior citation-support spot check remains only a convenience sample.
  Complete a broader, source-balanced support review and source-specific
  rights/attribution classification next; then build chunks only from eligible
  passages in an isolated versioned index and run the frozen paired writer
  questions. Do not start the 100-film run until those evidence and retrieval
  gates pass.

### Citation-support spot check (5 November 2026)

A local-only review selected one citation-bearing paragraph per film and
inspected its recorded locator, reference entry, and exact outbound target
where accessible. The smoke sample found two directly supported narrow
statements, one partial citation bundle, one current target/edition mismatch,
and six unresolved targets. It is a convenience sample, not a citation
accuracy estimate; inaccessible sources remain unverified rather than
incorrect. Per-film judgments are in ignored local
`data/evaluation/catalog-intake/first10-v1/citation-support-review-v1.md`.
This confirms citation markers/URLs are provenance locators only, not automated
support labels. Do not ingest or embed outbound source text from this check.
The boundary sample is now recorded separately in
`data/evaluation/catalog-intake/first10-v1/passage-boundary-review-v1.md`;
it found no structural mismatch in 30 selected passages. Next, expand the
source-balanced reference-support review and classify Wikipedia
attribution/share-alike duties separately from linked-source terms. Then run
retrieval over eligible local Wikipedia evidence against the frozen paired
questions. The 100-film expansion remains gated on those measured results and
rights review.

Raw snapshots, passage derivatives and the detailed audit remain local under
`data/evaluation/catalog-intake/first10-v1/` (ignored by Git). Only code,
documentation and small attributed fixtures belong in Git.

### Next actions, in order

1. **Continue ten-film reference-support and rights review.** The first
   boundary sample (30 Plot, Production and contextual passages) matches the
   retained source blocks; it is not corpus-wide approval. The existing
   one-paragraph-per-film citation check is a convenience sample with six
   targets still unverified. Expand source-balanced support review against the
   exact retained references; classify Wikipedia attribution/share-alike
   obligations separately from linked-source terms. Citation-marker and URL
   resolution are locators, not evidence validation or reuse clearance; keep
   anything unresolved out of the retrieval-eligible set.
2. **Complete the isolated vertical slice.** Turn only eligible passages into
   versioned chunks, build embeddings incrementally in the isolated evaluation
   index, then run the frozen paired writer questions. Label support per film,
   relevant passage IDs, acceptable abstention and reviewer rationale before
   viewing model results. Report retrieval separately from generation.
3. **Decide the 100-film gate from evidence.** Expand only after identity,
   source-policy, provenance, attribution, restart/resume, and paired retrieval
   checks pass. Keep unresolved and rights-ineligible records visible but out
   of the searchable corpus.
4. **Complete one explicit live contract run when DNS/network allows.** Verify
   robots retrieval, article response, EntityData response and the title/QID/
   year/IMDb cross-check sequentially, without writing to the working corpus.
   Until this run is possible, the captured fixtures prove parser/integrity
   behavior only, not the current live service contract.

The legacy admin intake currently starts from IMDb IDs/URLs and a local IMDb
lookup. That is a candidate-selection convenience, not a durable permission
or identity source. TMDB can improve candidate matching and metadata only
within its current API terms, attribution rules and allowed use. The
[official TMDB FAQ](https://developer.themoviedb.org/docs/faq) says its
free API use is for non-commercial purposes with attribution and directs
commercial projects to obtain a license. A future paid-product path must be
reviewed/licensed before relying on TMDB-derived data. Keep this policy gate
visible in the admin workflow.

## Explicit non-goals for this milestone

- Do not ingest SemEval/MF² answers or labels into the product catalog.
- Do not scrape private, blocked, login-gated or robots-disallowed endpoints;
  do not work around rate limits.
- Do not copy full reviews/essays or embed them without asset-specific rights.
- Do not mutate the working corpus before the isolated pilot passes review.
- Do not add a graph database, vector service, generic framework, new language
  or production deployment just because the eventual catalog may be large.
- Do not claim commercial readiness, 80% product accuracy, film completeness,
  or general writer utility from the pilot threshold alone.

## Decision log

- The newly audited public datasets are evaluation/research inputs first, not
  automatic product evidence.
- Wikipedia can provide unusually rich film context, but article availability,
  revision quality, rights attribution and field completeness vary by title.
- TMDB/Wikidata/Wikipedia complement rather than replace one another; each
  field remains bound to its own source assertion and scope.
- Reviews/essays are potentially valuable as attributed perspectives; links
  and bibliographic metadata are the safe default absent explicit text rights.
- The ten-film gate is the cheapest meaningful end-to-end proof before broad
  ingestion; scale the repeatable pipeline, not manual record repair.
