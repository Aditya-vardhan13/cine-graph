# CineGraph catalog and narrative data plan

Status: implementation in progress. Phase A baseline/pilot artifacts are
available; Phase B source-to-catalog quality work continues. No new source
material has been published to the working catalog. See the implementation log
at the end of this document. The [catalog preparation and expansion plan](catalog-preparation-and-expansion-plan-v1.md)
spells out the source policy, record contract and 10 → 100 → 1,000 gates.

## 1. The goal

CineGraph should help a writer study films, ask an original question, discover
relevant evidence across films, understand how different choices work, and
develop their own writing move. For example:

> How do *Avengers: Endgame* and *The Godfather* portray conflict between
> family loyalty and a character's idea of justice?

A useful answer identifies relevant actions and consequences in each film,
explains meaningful similarities and differences, cites supporting sources,
and admits when the available material does not support a claim. It does not
just list cast overlap, repeat a genre, or return long unrelated passages.

This plan separates three things that are easy to confuse:

1. **Catalog coverage:** whether we can identify a film and find its metadata.
2. **Evidence coverage:** whether we have attributable material relevant to
   particular writing questions.
3. **Answer quality:** whether retrieval and generation use that material to
   respond correctly and helpfully to the writer's actual question.

More records or vectors alone do not prove answer quality. The minimum possible
cost for a trustworthy answer is to identify the right works, locate sufficient
permitted evidence and evaluate the answer against it. Automate repeatable
mechanical work; keep human judgment for ambiguous identities, rights, meaning
and product usefulness.

## 2. Verified starting point

The following was checked against the local working database on 3 November 2026.
These are coverage indicators, not individual correctness guarantees.

| Measure | Current local count |
| --- | ---: |
| Film records | 2,586 |
| Film records with a Wikidata identifier | 2,586 |
| Films with at least one Wikipedia narrative passage | 1,487 |
| Films with a plot-labelled passage from any recorded source | 1,461 |
| Films with a production-labelled passage | 1,278 |
| Films with a reception-labelled passage | 1,345 |
| Films with at least one resolved director assertion | 2,575 |
| Films with at least one resolved cast assertion | 2,491 |
| Films with at least one resolved character assertion | 267 |
| Films with a date in the older film-profile field | 1,225 |
| Films with at least one resolved release-event assertion | 2,102 |
| Films represented by the existing embedding index | 1,000 |
| Stored vectors | 48,388, using `qwen3-embedding:0.6b` |

Passage and vector counts may include overlapping chunks, repeated source
revisions, or distinct processing runs; do not add them up as independent
facts. A `resolved` assertion is not proof that a human reviewed its accuracy.
The legacy `film_credits.character_name` field has no populated cast character
names; the newer character assertions do not, on their own, prove that every
actor-to-character pairing is complete or correctly shown in the UI.

The 1,000-film reference collection, existing 2,586 catalog records and a
source's list of 1,000 titles are different scopes. Freeze the exact intended
target list and version its identity before reporting percentage completion.
The supplied IMDb CSV is a selection input, not a guarantee of today's IMDb
ranking, English-only coverage, or coverage through 2025.

## 3. What we will do with the new datasets

### SemEval narrative similarity

The local preparation contains 1,219 distinct story summaries, including
non-film works, and comparison annotations. Its value is to evaluate whether a
method recognizes dimensions of narrative similarity such as theme, action and
outcome. It can also reveal candidates that might lead us to an underlying
source, subject to verification. See the [official dataset](https://github.com/narrative-similarity-task/narrative-similarity-dataset).

- **Now:** use development examples as a research control; keep a frozen,
  separately stored external test subset for final reporting.
- **Not now:** bulk-import all 1,219 as movies, turn labels into facts, or
  assume the story text is new to our catalog.
- **Possible future evidence:** only after independently verifying the actual
  film, source/article attribution, applicable license and reuse terms,
  revision limitations, duplication and holdout contamination. Store the
  approved source and provenance through the existing evidence pipeline.
- The release's official splits share text; our frozen 61-example subset is
  conservatively separated using supplied identities, but those identities are
  not independently verified and pretraining exposure is unknown.

### MF²

The acquired release contains 53 film transcripts, 53 synopses and fact/fib
questions. Its most useful immediate role is diagnosing whether retrieval and
answers can find evidence for a claim, understand who did what, and distinguish
unsupported or false statements. Some questions require visual information
that a text-only system cannot establish. See the [official MF² repository](https://github.com/deep-spin/MF2-bench-how-well-vlms-understand-movies).

- **Now:** use text-supported subsets as an evaluation control; record
  visual-dependent and insufficient-evidence cases separately.
- Preserve raw files and original timestamps, including invalid or untimed
  cues; do not invent speaker names. Quarantine the three identical fact/fib
  pairs rather than fixing their labels silently.
- **Not now:** put false claims or benchmark answers into film evidence, or
  assume the release license automatically clears each underlying subtitle.
- **Possible future evidence:** only if the film identity, transcription
  quality, asset-specific rights and attribution are individually established;
  document the use and isolate evaluation contamination.

### Existing IMDb data, TMDB, Wikidata and Wikipedia

Use each source for what it actually supplies, with its source-specific policy:

| Source | Intended role | Important constraint |
| --- | --- | --- |
| Local IMDb datasets | Candidate titles, identifiers, aliases, credits and ranking signals, where available | The published datasets are for personal/non-commercial use; do not assume they can be used in a paid service. [IMDb terms](https://data.imdb.com/non-commercial-datasets/) |
| TMDB API | Film identity candidates, metadata, cast/character mappings and other available fields | Respect attribution and current API terms. TMDB distinguishes commercial API access; review before monetization. [TMDB FAQ](https://developer.themoviedb.org/docs/faq) |
| Wikidata | Cross-source identifiers, multilingual labels, dates, credits and typed relations when supported | Statements and references still need conflict handling; a matching ID alone does not establish every property. |
| Wikipedia | Source-linked plot, production, reception, thematic and legacy context where available | Retain source revision, attribution and license information; article depth varies. |
| Independent reviews / essays | Attributed critical perspectives and filmmaker intent where permitted | Publication is not a blanket license to scrape, reproduce, embed or redistribute text. Store links or acquire rights as appropriate. |

All source adapters must follow their applicable terms, robots rules for
crawling, rate limits and access policies. For Wikimedia Action API access,
separately verify the API policy and our strict robots requirement for the
specific route before enabling automated retrieval; do not assume a browser
page being visible authorizes scraping. Wikimedia recommends an informative
user agent and sequential API requests. [MediaWiki API etiquette](https://www.mediawiki.org/wiki/API:Etiquette).
Stop on access denial or rate limiting; do not bypass controls.

## 4. What a well-prepared film record should contain

Not every source has every field. The catalog must represent **unknown**
explicitly and avoid filling gaps by invention. The coverage dashboard should
measure each field or evidence category separately, not give one misleading
"complete" percentage.

| Layer | Information | Example and caveat |
| --- | --- | --- |
| Identity | Canonical title, aliases, original-language title, year or release events, external IDs, work type | Separate remakes, same-title releases and film vs series or novel. |
| Basic metadata | Runtime, original languages, countries, genres, release events | A festival date and wide release date are distinct events, not necessarily conflicting facts. |
| People and roles | Directors, writers, producers, principal cast, crew and actor-to-character credits where sourced | Preserve source, role, character name, ordering and disagreements. Do not infer an actor-character pairing from co-occurrence. |
| Story evidence | Plot, protagonist goals, conflicts, choices and consequences where a source supports them | Plot text is source evidence; an inferred theme is an interpretation, not a verified metadata field. |
| Craft and creation | Development, writing, casting, cinematography, editing, sound, music and production decisions | Store only sections actually present and attributable. |
| Reception and significance | Contemporary reviews, awards, box office with dates and currency, legacy and career context | Attribute opinions and scope superlatives; do not treat popularity as universal approval. |
| Relationships | Confirmed sequel/adaptation/source-work connections and sourced influences | Distinguish a typed relationship from a retrieved thematic resemblance. |
| Rights and provenance | Source, URL, revision/date, license, capture hash, locator and access scope | Display appropriate attribution; missing or unclear rights means no automatic publication. |
| Derived retrieval data | Versioned passages, chunks, embeddings and retrieval indexes | Derivatives are replaceable and reproducible; they are not canonical facts. |

For a writer, a film page should show what exists, cite it, and clearly state
what is missing. It should not imply that all films have a plot, full
filmography, director intent, reviews, scripts or a complete creative analysis.

## 5. Catalog preparation pipeline

Use the existing application boundaries and local PostgreSQL/pgvector. Do not
introduce a second fact graph or a new database service merely for novelty.

```text
title list / admin-selected titles / permitted source links
  -> resolve candidate identity and display disambiguation
  -> capture authorized source snapshots + source policy
  -> parse and normalize into source assertions and narrative passages
  -> check identities, conflicts, provenance, rights and coverage
  -> publish eligible facts and passages; quarantine exceptions
  -> chunk -> embed -> index versioned evidence
  -> retrieve -> ground a question-specific answer -> evaluate
```

### 5.1 Intake and identity

- The admin can search, select multiple distinct movies, inspect title/year/
  language/external ID and submit a batch. A pasted approved source URL is a
  candidate input, not permission to crawl arbitrary websites.
- A job records requested input, identity candidates, decisions, source policy,
  stage, attempts, errors and resume state. Re-running the same job should
  reuse identical source data rather than duplicate films or credits.
- Use exact external-ID agreement when trustworthy; compare title, release
  years, work type, language and other fields as corroboration. If candidates
  conflict, route them to review instead of choosing by title alone.
- Preserve remakes, alternate editions, multilingual names and original titles.
  Do not silently label multilingual works as English-only.
- A future public request queue is separate from administrative ingestion;
  real admin privileges require authentication and server-side authorization.
  An email address alone is not authentication.

### 5.2 Capture and normalize

- Capture source responses locally, with revision, retrieval time, content hash,
  source policy, license and attribution. A snapshot is immutable; an update
  creates a new version.
- Parse JSON/CSV/XML with appropriate parsers and use regex for suitable text
  patterns. Normalize whitespace and identifiers with versioned scripts, not
  manual edits to each film. Preserve raw text and original values.
- Map structured source statements into `SourceAssertion`; publish appropriate
  typed facts through the existing `Assertion` projection. Keep narrative
  passages as contextual evidence, not automatically approved factual claims.
- Keep release events, countries, language codes and source disagreements
  structured. Store `unknown` rather than converting missing values into facts.
- For Wikipedia, compare current and candidate parser outputs against the same
  retained revision, including text across chunk boundaries and source
  references. Before publishing a second extraction version, implement and test
  explicit version selection: the current `current_passage_rows` read path can
  otherwise return multiple versions of one snapshot.

### 5.3 Quality and publication

Each film receives machine-readable, source-scoped states such as: identity
verified/review needed; metadata present/missing/conflicted; plot present;
production or reception present; rights eligible/review needed; source
snapshot available/checksum failure; indexed/not indexed. These states are
not a substitute for reviewing the meaning of content.

Narrative model-use eligibility is recorded per immutable `SourceSnapshot` and
per named purpose, not as a source-wide switch. The append-only decision ledger
retains version, reviewer, rationale and a basis URL. Only the latest explicit
`approved` decision for `semantic_index_and_model_input`, together with the
snapshot's supported license and attribution, can feed chunking, embeddings,
retrieval or model context. Missing decisions default to excluded; a later
denial or deferral revokes eligibility without deleting previous review
history. The local operator UI records a review decision; it is not a legal
determination or authentication system for public deployment.

Quarantine ambiguous IDs, invalid source data, broken snapshot checksums,
conflicting claims and unclear rights. Do not discard them silently. A review
can approve, reject or defer an item and must preserve the reason and source.
No overwrite of the original source or another source's assertion.

### 5.4 Evidence preparation and indexes

- Build passages from attributable source sections. Keep source locators,
  parser version and revision. Where feasible retain offsets into the underlying
  captured source; for transformations without exact offsets, state the
  limitation rather than manufacturing them.
- Chunk around readable semantic units with overlap only when useful. Keep
  both the focused passage and enough surrounding context for disambiguation.
  Avoid indexing duplicate text across source revisions as independent support.
- Store a versioned chunk configuration, embedding model, model revision,
  index run and status. Index only eligible content; retry failed work without
  rewriting successful immutable artifacts. Reuse an existing vector only when
  the complete model/input contract and source text are exactly the same.
- Start with the existing local Qwen embedding baseline and PostgreSQL/pgvector.
  Test alternatives on the same frozen evidence and questions. Adopt a larger
  embedding model or reranker only if measured answer-support gains justify
  latency, memory and cost. A vector retrieves candidates; it does not prove a
  relationship or turn a source's interpretation into a fact.

## 6. Retrieval and generation for the actual writer flow

1. The user chooses two films and asks a specific question. The system preserves
   the exact question and identifies its required aspects without inventing
   events or assuming both films contain the premise.
2. Retrieve within each selected film using a combination of lexical and dense
   search where that proves useful. Include source-type and section metadata;
   use a reranker only if its measured benefit justifies its cost.
3. Select small, diverse, source-bound evidence bundles per film. Track which
   part of the question is supported and which is missing. A good match for one
   film does not excuse irrelevant evidence for the other.
4. Pass the question and selected passages to a local quantized generator for
   an answer. Generation must reference evidence, distinguish fact from
   attributed interpretation, compare concrete choices and consequences, and
   say when available evidence is insufficient.
5. Provide an optional user-supplied model provider/key later, behind a secure
   implementation. Never commit keys or send local evidence to an external
   provider without informing the user; provider terms and data retention must
   be clear. A key is not required for the local development path.
6. Show the answer, source passages and a clearly marked writing prompt or
   creative move. Let a writer inspect source context, not just trust a score.

Use of reviews and essays should enrich interpretation, not turn a critic's
opinion into objective truth. A useful comparison may say two films explore a
similar dilemma through different choices; it must not claim direct influence
unless the evidence actually establishes influence.

## 7. Phased execution and visible outcomes

### Phase A — freeze the target and baseline

1. Version a reproducible English-first pilot list of 100 films. The earlier
   global top-100 manifest is a separate multilingual diagnostic, not this
   English pilot. Select unique exact title/year matches against the existing
   catalog whose recorded catalog language is `en`; retain input rank, year,
   catalog ID and explicit skipped-row counts. The local IMDb CSV supplies
   candidate ordering only: do not reuse its non-commercial data fields or
   describe it as a current official ranking. Add user-requested comparison
   films only through a separately recorded, sourced exception if they are not
   in the deterministic selection.
2. Run a read-only coverage and integrity report for each film: identity,
   metadata, actor-character mappings, source availability, plot, craft,
   reception, license scope and index status. Include missing and conflicted
   counts, not only successes.
3. Freeze the baseline of real user questions, retrieval outputs and latency
   before changing models or parser versions.

**Outcome:** a film-by-film coverage sheet and an honest baseline against which
all later changes can be compared.

### Phase B — repair the source-to-catalog foundation

1. Add the parser-version selection rule and prove it with isolated database
   and API tests. A newer parser is not automatically authoritative.
2. Audit and reconcile release-event presentation and actor/character mappings
   using source assertions; preserve regional/date semantics and conflicts.
3. Make snapshot integrity and source eligibility visible in the audit report;
   preserve recovered source revisions and never overwrite evidence.
4. Run the candidate Wikipedia parser against the 100-film pilot and review a
   stratified sample of changed passages, captions, multilingual templates,
   citations and chunk boundaries. Publish a new version only after the gates
   below pass.

**Outcome:** correctly attributable records and an explicit report of which
pilot films and fields remain missing or need review.

### Phase C — enrich the first 100 films

1. Use approved sources and the batch intake pipeline to fill identified gaps.
   Review ambiguous matches and rights; do not force every film into a fixed
   template if a source does not contain that information.
2. Use SemEval and MF² to test the pipeline and identify candidate sources,
   subject to the separation rules in section 3. They are not a bulk factual
   import.
3. Compare the baseline and new coverage by film and category. Manually audit
   a stratified sample, including multilingual titles, remakes, missing pages,
   actors with multiple roles and sources that disagree.

**Outcome:** a reviewed 100-film pilot with sourced metadata and narrative
evidence; a per-film report shows what is present, absent or unresolved.

### Phase D — question-led retrieval and answers

1. Keep the existing **10 film pairs × 5 questions = 50 cases** as an inspected
   development/regression set, not a holdout: rankings and passages have
   already been reviewed during tuning. Use it to reproduce and compare
   iterations, but do not use its score as an independent quality claim. In
   parallel, prepare a separately frozen film-pair-disjoint holdout before
   evaluating a release candidate. Include family, loyalty, injustice,
   character choices, consequences, craft and contrast in both sets; never
   tune against the holdout.
2. Mark independently whether each film actually has sufficient retained
   evidence for the question. Include supported, partially supported and
   unsupported-premise cases. Count repeated pairs and films; 50 questions on
   10 pairs are not 50 independent film-pair trials.
3. Compare lexical, existing hybrid and alternative model configurations on the
   same evidence and budgets. Record per-film evidence relevance, both-film
   coverage, source support, retrieval latency and failure causes.
4. Generate answers from the same evidence bundle; separately review accuracy,
   correct character attribution, question coverage, source support,
   appropriate abstention, comparative insight and writer usefulness.

**Proposed development gate, not a current achievement:** on the 50
development/regression cases, relevant supporting evidence is found for *both*
films on at least 80% of cases independently judged supportable for both.
Report the exact numerator and denominator and all partially supported or
unsupported cases separately. Passing this set only shows that an iteration
meets a development target; it cannot qualify a release. The same metric must
then be measured once on the untouched film-pair-disjoint holdout. Also report
unsupported claims, misattributions and abstention failures; a retrieval
percentage alone does not qualify an answer as good. Because 50 cases and 10
pairs are small, show per-pair results and uncertainty and validate on
additional unseen films before claiming general performance.

**Outcome:** a reproducible comparison demonstrating whether the system is
actually answering writer questions better than its own baseline.

### Phase E — extend from 100 to the selected 1,000

1. Fix recurring failures as pipeline rules or source adapters, not one-off
   edits to individual movie records. Re-run the relevant regression set.
2. Run batches with bounded concurrency, checkpoints and durable reports;
   source-specific limits, errors and review queues remain visible. Do not
   restart a quiet job without checking its actual process and artifacts.
3. Recompute coverage and source-integrity reports as each batch completes.
   Only publish eligible records and build index runs for eligible evidence.
4. Audit a new stratified sample and run the frozen question tests plus new
   film-disjoint cases. Distinguish `requested`, `resolved`, `evidence-ready`,
   `indexed` and `review-required`; 1,000 requested is not 1,000 vetted.

**Outcome:** a versioned, measurable 1,000-film reference collection with
transparent gaps and a tested question-answering workflow.

### Phase F — make expansion routine

Once the 1,000-film pipeline works, make the same intake, source policy,
identity checks, monitoring, selective reprocessing and review queue usable
for later English and Indian-language additions. Maintain multilingual identity
and search without translating away source language or claiming coverage that
does not exist. The architecture should allow growth toward 100,000 films, but
we will not provision a 100,000-film cluster now.

## 8. Testing and acceptance gates

- **Unit:** deterministic parsing, identity matching, normalization, rights
  decisions, deduplication and query policies. New tests use no mocking/patch
  framework and no live network.
- **Integration:** real PostgreSQL/pgvector and migrations in `cinegraph_test`
  only; exercise source snapshot → assertions → passage → chunk → index and
  safe retries. Never truncate or test against the working corpus.
- **API and browser:** test search/disambiguation, character names and release
  events, admin authorization, batch progress, user comparison, citations,
  errors, partial evidence and responsive UI against a separate local test
  stack.
- **Source QA:** verify file hashes, revision and license metadata; confirm
  displayed passages and links correspond to their source. Test live source
  contracts only as explicit, bounded, permitted manual checks.
- **Retrieval/generation:** run frozen, question-led evaluation; review source
  support, answer quality and latency separately. Preserve all failures and
  denominators. Have an independent writer review a representative sample
  before claiming the product helps creativity.
- **Reliability:** prove idempotent resume, visibility of failed jobs, safe
  reprocessing and recovery from a retained local backup. Store raw data,
  databases, vectors, model weights and snapshots locally; Git holds code,
  migrations, documentation and small fixtures only.

## 9. Cost and scalability choices

- Local development first; no deployment is required for these phases.
- PostgreSQL with pgvector is the current shared metadata and vector store. It
  supports a practical starting point; measure latency, recall, throughput,
  indexing time and operational cost as data grows. A separate vector service
  or graph database is a later decision based on observed bottlenecks, not a
  prerequisite for 1,000 films.
- Measure real-time work separately from offline work. Acquisition, parsing,
  indexing and document embeddings are offline/incremental. A user question
  requires query embedding, candidate retrieval, optional reranking and answer
  generation at request time. Cache safe, versioned results where measurement
  shows repeat use; invalidate on source/index/model changes.
- Stay within local memory and disk headroom. Record model download size,
  runtime memory, inference latency and quality on the same evaluation before
  switching models. Do not confuse RAM required by a local model with the
  storage required for existing vectors.
- Before any paid or public deployment, review license eligibility, user data,
  hosting and model-provider costs, and a budget against actual traffic. IMDb
  non-commercial data and a TMDB developer key are not automatic commercial
  rights. The previous ₹2,000/month preference is a budget constraint to test,
  not a promise that every traffic level can be served at that price.

## 10. Immediate decision and open questions

Recommended execution order: **A → B → C → D → E**, with a visible report at
each gate. Do not wait for all 1,000 to evaluate a writer-facing flow; prove it
on the first 100, then extend the same pipeline.

Questions to settle during Phase A, without blocking safe baseline work:

1. Which exact 1,000-film target constitutes acceptance? The supplied global
   list is only a candidate source: the latest local audit maps 730 rows to
   English-labeled catalog candidates, 50 to known non-English candidates,
   189 to unresolved/multilingual language, and 31 to unresolved identity. It
   cannot alone satisfy an English 1,000 target. Keep it as a multilingual
   diagnostic; define and version any additional English candidate sources
   and language/identity gates before expansion. Important comparison films
   outside the deterministic list remain separately sourced exceptions.
2. Which source licenses and attribution obligations permit the intended pilot
   and, later, a paid product? Record decisions per source and derivative.
3. Which films lack sufficient sources for a given question, rather than merely
   lacking a model that can answer it?
4. Can the local model configuration meet acceptable latency and useful-answer
   standards on the same independently reviewed evidence? This is unproven.

No calendar estimate, promised coverage, model superiority or commercial
readiness is asserted until the baseline and source constraints are measured.

## 11. Implementation log

### Phase A implementation — 3 November 2026

- Added `scripts/catalog_readiness_report.py`, a database read-only per-film
  report. It captures profile fields, aliases, resolved assertion counts,
  credits/character-name counts, release years from resolved release events,
  narrative section categories, snapshot attribution indicators and embedding
  vector counts. It does not claim that a nonempty field is correct or licensed
  for commercial use.
- Generated local-only report versions under ignored
  `data/evaluation/catalog-readiness-v1.json` through `v3.json`. The latest
  covers all 2,586 catalog films. Reports are versioned rather than overwritten.
- Added `scripts/freeze_catalog_pilot.py` to fingerprint the input CSV and
  readiness report and compare the first 100 CSV rows against catalog canonical
  titles, release-event years and known catalog aliases. It reports candidates;
  it never merges or changes film identities.
- The frozen local `catalog-pilot-top100-v3.json` contains 77 exact canonical
  title/year candidates and 23 that need identity review. No exact catalog
  alias/year matches were found for the remaining 23. The input CSV's order is
  retained; it is not represented as a current or authoritative ranking.
- Follow-up identity review used the local IMDb title index, not the IMDb
  website. All 23 romanized/alternate-title exceptions had an IMDb title/year
  candidate whose `tconst` also appears on exactly one catalog film's resolved
  IMDb identifier. The final local `catalog-pilot-top100-v5.json` therefore has
  one candidate catalog record for each of 100 rows: 77 canonical exact
  title/year matches and 23 **review-required** ID crosslinks. Examples include
  `Gisaengchung` → `Parasite` and `Sen to Chihiro no kamikakushi` → `Spirited
  Away`. The crosslinks are not merges or approval; inspect the linked source
  assertions and movie identity before accepting them. The IMDb dataset is
  non-commercial and these local artifacts remain ignored/uncommitted.
- A second read-only audit queried the existing evidence chain for each of the
  23 linked IDs. All 23 have a `resolved` `imdb_identifier` assertion whose
  evidence is a Wikidata `P345` source assertion with the same IMDb ID; all 23
  link to unique Wikidata and IMDb IDs and have source attribution URLs. The
  evidence report is local at
  `data/evaluation/catalog-pilot-identity-evidence-v1.json`. This validates the
  recorded crosslink provenance, not independent film content, rights, or
  permission to use IMDb dataset fields commercially. Keep the 23 flagged
  until their review decision is recorded.
- Updated `current_passage_rows` to choose only the approved extraction version
  for known source-parser adapters and to fail closed if an unknown adapter has
  multiple extraction versions. Added an integration fixture proving that an
  experimental second extraction is not also returned. The isolated test suite
  `test_current_narrative_passages.py` passes: 3 passed against `cinegraph_test`.
- No new film data, assertions, passages or vectors were written to the working
  database. Next: resolve/triage the 23 candidate identities, add unit tests and
  a reproducible gate for the pilot manifest, then audit and enrich missing
  fields only through the existing source-provenance intake pipeline.

### Follow-up implementation — pilot manifest gate

- Added `backend/app/services/catalog_pilot_manifest.py` as a pure validator
  for the frozen pilot's input fingerprints, row-to-CSV correspondence,
  identity-state structure, candidate counts and exact-title/year evidence.
  Crosslinks must remain explicitly review-required; structural validation
  never declares a film identity correct or its source commercially eligible.
- Added `scripts/validate_catalog_pilot.py`, an offline read-only CLI restricted
  to local `data/evaluation` artifacts and the supplied project CSV. It does
  not open the database or alter the manifest.
- Added seven fixture-based unit tests (no mocks or network). All seven pass.
- Ran the validator against local `catalog-pilot-top100-v5.json`, its exact
  readiness report, IMDb candidate-review artifact and CSV. Result: 100 rows,
  77 `exact_title_year`, 23 `review_required_unique_imdb_crosslink`, 100 unique
  candidate film IDs; all three input fingerprints match. This proves
  reproducibility and structure only, not the unresolved identity decisions.
- No working-corpus rows or files outside the project were changed. The
  operational roadmap is in
  [catalog-expansion-execution-plan-v1.md](catalog-expansion-execution-plan-v1.md).
- At that checkpoint, next steps were to reconcile the pilot's legacy
  profile date/runtime fields with research assertions, record crosslink
  dispositions and exercise the local intake pipeline before batch enrichment.

### Intake lifecycle and rights visibility — 6 November 2026

- Corrected the local intake worker's successful terminal states to
  `captured` / `captured_with_gaps`. The previous `ready` labels overstated
  completion: this worker captures source data and extracts passages but does
  not approve rights or run chunking/embedding. Existing persisted `ready`
  records remain readable and are explicitly labelled as legacy capture states.
- Extended the per-film preview with counts for current narrative snapshots
  with passages: approved, pending, denied, and currently eligible for
  semantic processing under the shared explicit-license, attribution and
  snapshot-decision policy. No decision is created or inferred by this read.
- The intake page now explains that capture, rights review, chunking and
  embedding are distinct stages, and links directly to the snapshot rights
  desk. The count is limited to snapshots represented by the film's current
  passages; it is not a full catalog or index completion metric.
- Updated the isolated API integration stack to use the explicitly local
  operator gate and added a real PostgreSQL/API contract covering a pending
  snapshot beside an approved fixture. The test asserts that intake does not
  claim to perform indexing. The integration database remains
  `cinegraph_test`; it does not touch the working corpus.
- Fixed the integration runner's missing repository-root `PYTHONPATH`, and
  configured Playwright to launch a separate Next dev server/build directory
  with the integration API as its backend. This prevents browser tests from
  accidentally proxying through the working development API.

### Follow-up — explicit pilot crosslink dispositions

- Added a pure, fail-closed adjudication policy and local CLI that bind the
  frozen pilot, IMDb candidate-review artifact and Wikidata identity-evidence
  artifact by SHA-256 before producing decisions. It requires one unique
  catalog film/QID, one matching title/year candidate at score ≥ 0.80, and at
  least one resolved, attributed Wikidata P345 assertion whose value matches
  the candidate IMDb ID.
- All 23 crosslinks pass and are accepted as the same work **for pilot-list
  membership only**. The lowest resolver score is 0.8148 for `Sunset Blvd.` →
  `Sunset Boulevard`; this is retained explicitly rather than described as an
  exact title match. The other 22 score at least 0.9. The frozen candidate
  manifest remains unchanged and still marks these links `review_required`;
  this sidecar does not merge catalog entities or authorize IMDb field reuse.
- The ignored local decision artifact is
  `data/evaluation/catalog-pilot-identity-decisions-v1.json`; its input hashes,
  evidence assertion IDs, decision scope and non-merge/non-reuse flags are
  recorded. It is not committed because it contains local dataset-selection
  identifiers and is reproducible from the pinned local artifacts.
- Added three policy tests for valid narrow decisions, missing P345 evidence
  and weak/mismatched title candidates. The targeted policy suite passes
  11/11; the full non-integration backend suite passes 233/233; the end-to-end
  command produced 23 decisions. No database rows or existing source
  assertions were changed.
- Remaining Phase 1 work: finish the pilot release-date/runtime review,
  characterize the zero default-display actor-to-character coverage, and
  verify the local intake process before any film data is published.

### Follow-up implementation — source-eligible research metadata

- A read-only SQL audit found the original shared research projection mixed
  open Wikidata assertions with `local_noncommercial_only` IMDb/TMDb metadata.
  Conflicting runtime values caused the conservative policy to return no
  runtime for all 100 pilot films, even though source-by-source evaluation
  yielded a single displayable Wikidata runtime for 82. It also queried sources
  marked `metadata_link_only` or `review_required` as though they were
  displayable.
- Added the pure `source_rights_policy` with explicit eligibility states.
  Research film metadata, release-era signals and sourced credit groups now
  filter through it. Default display permits `open`, `attributed_reuse` and
  `attribution_required`; local non-commercial use is an explicit opt-in;
  link-only and unresolved rights are excluded. Research API results now retain
  source name, license and rights status for each metadata assertion.
- The film profile no longer substitutes legacy profile date/runtime values
  when the research profile exists but has no eligible value. The old values
  remain visible only when no research profile is available. Existing sourced
  release conflicts remain explicit.
- Re-audited the pilot through the implemented default read model (read-only):
  100 release years, 70 exact dates, 82 runtimes. This is a projection result,
  not a human factual audit or evidence that these fields meet a paid product's
  licensing requirements.
- Added policy unit tests and a real PostgreSQL test demonstrating that
  non-commercial data only affects local output when explicitly opted in,
  while link-only and unresolved sources remain excluded. Full
  `test_research_read_models.py`: 13 passed against `cinegraph_test`; full
  repository integration runner: 69 passed; normal backend suite with the
  local parser vendor fallback: 229 passed, 60 skipped; frontend production
  build passed. The integration runner's API contract run uses only the
  dedicated `cinegraph_test` stack.
- No corpus rows, source snapshots, passages or vectors were changed. Next:
  trace the legacy `Film` projection conflict by field/source assertion, then
  resolve pilot identities and source eligible actor-to-character data before
  any 100-film write batch.

### Follow-up — release events keep their territory context

- A read-only source audit explained one of the most visible date anomalies:
  *The Dark Knight Rises* has a 2022-10-06 event qualified to place Q851 in the
  same Wikidata revision that records its 2012 releases. It was a later
  territory event, not evidence that the film premiered in 2022. The previous
  profile compared years but had dropped the event qualifiers, so it called a
  valid alternate event a conflict.
- The API now returns every eligible, parseable release event with its date or
  year, place IDs, source, revision, review state, license and rights state.
  The film page labels the first recorded event separately and exposes the
  other dates as inspectable evidence; a legacy date that matches a recorded
  event is not presented as a conflict. Unsupported mismatches remain a
  warning. No source assertion or working profile value was edited.
- Verification: 238 backend unit tests passed (60 skipped); the isolated
  `cinegraph_test` integration/API suite passed 69; Playwright passed all 7
  browser flows including the release-event list; Next.js production build
  passed. Working-catalog inspection was read-only.
- This is one resolved presentation case, not a complete release-event audit.
  The 100-film legacy profile date/runtime audit and any operational identity
  merges remain open; the selection-only dispositions for 23 crosslinks and
  source-eligible actor-to-character audit are recorded below. The product is
  not yet ready for batch enrichment or a writer-quality claim.

### Follow-up — character-credit coverage is rights-qualified

- A read-only query joined the frozen top-100 manifest to source-backed cast
  assertions. All 100 films have at least one character-bearing assertion in
  the local corpus, but every one of those matches is from a source marked
  `local_noncommercial_only` (IMDb); four films also have TMDb character
  assertions under the same local-only state. The query found 1,038 IMDb and
  81 TMDb character-bearing assertions. It found no default-display-eligible
  character assertion for this 100-film set. This is the concrete reason a
  page can show cast names without a use-eligible actor-to-character mapping;
  presence in the local database is not permission to display it by default.
- A separate read-only aggregate found 26 default-display-eligible
  (`attributed_reuse`, CC BY-SA 4.0) English-Wikipedia cast assertions
  elsewhere in the working catalog, 25 of which contain a character label;
  these records are Telugu films, not a substitute for resolving the English
  pilot's gap.
- Updated `audit_movie_collection` to report separately (a) character-credit
  presence from any recorded source-rights state, (b) character-credit
  coverage eligible under the default display policy and with a citeable
  HTTPS source URL, and (c) local-non-commercial-only character coverage. The
  old `with_any_character_credit` now clearly means any recorded source, not
  product-eligible coverage. Missing default-display coverage is called out
  separately in per-film gap output.
- Added a real PostgreSQL integration case with two films: one has both open
  and local-only character evidence; one has only local-only evidence. It
  verifies 2 films with any mapping, only 1 default-display-eligible, and 2
  local-only. Verification: isolated integration suite 70 passed; non-
  integration backend suite 229 passed. Both used the Conda `cine-graph`
  environment; tests ran only against `cinegraph_test`. No working-catalog
  rows were changed.
- Next: obtain a reusable, default-display-eligible source for character
  mappings or intentionally label the field unavailable for the pilot. Do not
  expose the existing IMDb/TMDb-only rows by toggling a product setting until
  intended-use rights are established. Continue the remaining pilot identity
  and release-date/runtime audit before batch enrichment.

### Follow-up — release-date precision remains visible

- The research release-event projection now carries the original Wikidata
  time precision through the API, and the film profile labels events as
  year-, month-, or day-precision instead of making a year-only assertion
  look like a complete date.
- The projection accepts only calendar year/month/day precision. Sub-day
  precision is excluded rather than silently truncated into a date; the
  original source assertion remains untouched for future policy changes.
- Added pure tests for year/day precision, response-model preservation and
  rejection of sub-day values. Focused backend tests pass (8/8), the frontend
  production build passes, and the isolated API/PostgreSQL suite passes (70
  tests against `cinegraph_test`). Browser verification remains a separate
  gate.
- No working-corpus records, source snapshots, passages or vectors changed.
  The full 100-film release-event/runtime review remains open; this change
  improves precision fidelity but does not certify the underlying dates.

### Follow-up — pilot date/runtime audit tooling

- Added `backend/scripts/audit_pilot_metadata_projection.py`, a write-once,
  read-only report command for the frozen 100-film
  manifest. For every candidate film it compares legacy profile date/runtime
  with the same rights-filtered research projection used by the API and
  includes underlying release/runtime assertions with source, rights,
  revision, qualifiers and review state. Distinct statuses explain matches,
  territory-qualified later events, year-only evidence, conflicts, restricted
  sources and missing evidence.
- Pure tests cover the classifier cases (5), and combined with research
  metadata tests the focused run passes 13/13. The report was run read-only
  against the local `cinegraph` database and the frozen 100-film manifest; its
  JSON output stays under ignored `data/evaluation/`. No database rows or
  source data were modified.

### Follow-up — 100-film metadata audit results and next catalog gates

The per-film report shows why the old profile fields looked empty or wrong:
the API's rights-filtered research projection has evidence that the legacy
`Film` columns do not consistently carry, while the same source data also has
real ambiguity that should not be flattened into one unqualified value.

| Field | Pilot audit result | Meaning / action |
| --- | ---: | --- |
| Legacy release date | 19/100 populated; 81 missing | Do not treat an empty profile date as absence of release evidence. |
| Existing release date maps to earliest recorded event | 3 exact; 2 match the earliest year but event order is unknown | Preserve precision and territory; avoid calling a year-only event an exact date. |
| Existing release date maps to another recorded event | 13 | These are supported territory-specific dates, not automatically wrong; label event scope and do not present as the first release. |
| Same-year release date without exact event match | 1 | Route for review; Psycho's legacy Jan 1 date is not an exact match to its dated release events. |
| Runtime | 17 exact matches; 65 eligible research runtimes missing from legacy profile | The research profile can fill these at read time; any operational backfill must be separately reviewed and provenance-preserving. |
| Runtime conflicts / edition ambiguity | 17 require resolution | Keep runtime unset in the default view until edition, cut, territory or source precedence is resolved. |
| Restricted-only runtime evidence | 1 | Do not display by default; Soorarai Pottru currently has only a local non-commercial IMDb runtime assertion. |

The audit is a projection and provenance audit, not an independent truth
review. It establishes neither universal factual accuracy nor commercial reuse
rights. Its report is local-only and ignored by Git. The audited assertions
retain source revision, rights/license, qualifiers and review status.

Next steps are ordered to avoid scaling bad records:

1. Resolve the 17 runtime-ambiguous films and one date exception by inspecting
   source assertions and version/territory qualifiers. If evidence does not
   establish one display value, keep the field explicitly unresolved.
2. Add source-specific intake adapters only after recording terms, license,
   rate/access policy, attribution and fields supplied. Dataset admission is
   field-level: useful structured metadata may enter its own provenance lane,
   but does not grant rights to unrelated plot/review text bundled with it.
3. Exercise one full title-to-evidence vertical slice on a small stratified
   batch: disambiguate identity; snapshot authorized sources; extract typed
   assertions and sectioned passages; validate identity, rights, checksum and
   coverage; review; index eligible passages; retrieve cited evidence. Keep
   every stage resumable and idempotent, and publish gaps rather than silently
   filling them.
4. Only then enrich the 100-film pilot, compare per-film coverage against the
   frozen baseline, and expand to 1,000 in checkpointed batches. Do not claim
   a 1,000-film-ready corpus from the size of a source dataset alone.

The broader catalog remains additive and language-neutral. Each incoming
dataset must pass identity-link, field-definition, license/attribution,
provenance, duplicate, conflict, coverage and sample-quality checks before it
is eligible for batch ingestion; raw payloads, snapshots and derived vectors
remain local and out of Git.

### Follow-up — browser contract exposed and fixed an incomplete test fixture

- The first Playwright run passed the film-profile release-date event but
  failed 4/7 flows: comparison returned 422 and single-film passages returned
  503. The isolated seeder had created source passages but no completed
  `EvidenceChunkRun`; both API routes correctly refused to serve an unprepared
  collection. This was a test-fixture/preparation defect, not a reason to
  weaken route behaviour or browser assertions.
- The isolated seeder now runs the real versioned evidence chunker after
  creating its retained passages, checks the expected four eligible fixture
  passages, and still creates no embeddings or external requests. Added a real
  PostgreSQL/API contract for the UI's default hybrid comparison request with
  no retrieval-method override, including source-attributed two-sided evidence
  and lexical fallback when semantic retrieval is unavailable.
- Verification: 71 API/PostgreSQL integration tests passed in
  `cinegraph_test`; all 7 Playwright flows passed against that same seeded
  stack. No working-catalog rows, snapshots, passages or vectors were changed.
  The projection audit's unresolved release/runtime source review remains the
  next catalog-data gate.

### Follow-up — robots-compliant source routes and current gate (4 November 2026)

- Verified current Wikimedia route policy before capture: Wikidata's
  `Special:EntityData/{QID}.json` suffix route is allowed and supports a pinned
  `revision=` parameter; generic Wikidata `/w/api.php` and Wikidata Query
  Service `/sparql` are disallowed. English Wikipedia ordinary `/wiki/{title}`
  article pages are allowed; generic `/w/api.php` is disallowed. One permitted
  but obsolete `mobileview` request returned `badvalue`; no alternate API route
  was attempted.
- Updated the Wikidata adapter to known-QID, sequential EntityData JSON
  capture (one request/second, concurrency one) and disabled blocked title
  search. Wikipedia API lookup and revision recovery now fail closed. This is
  route compliance, not an HTML ingestion implementation: the next source
  adapter must capture normal article HTML immutably and extract versioned,
  section-located passages with revision, attribution and parser diagnostics.
- A pinned Wikidata response for one missing historical snapshot did not match
  the stored historical hash. It was not linked to or substituted for the old
  snapshot; all six old snapshot gaps remain explicit. Captures stay local.
- Latest isolated API/PostgreSQL integration run: **73 passed, 242 deselected**
  with two third-party warnings in `cinegraph_test`; the browser flow remains
  **7/7 passed**. No working-catalog rows, passages, assertions or vectors were
  published by this route-policy work.
- Detailed source-route findings and the updated execution sequence are in
  [the catalog preparation and expansion plan](catalog-preparation-and-expansion-plan-v1.md).

### Follow-up — ordinary Wikipedia article capture implemented (5 November 2026)

- Added a robots-checked, sequential capture adapter for ordinary English
  Wikipedia `/wiki/{title}` pages. It retains response bytes and records page,
  revision, QID and section metadata as source assertions; extracted prose is
  versioned `NarrativePassage` evidence and never promoted into typed facts.
  Capture requires an already-known QID/sitelink. Generic Action API lookup
  remains disabled.
- The parser accepts only ordinary HTTPS enwiki article URLs, checks the
  robots policy again after redirects, waits at least one second between
  requests, bounds redirects and payload size, and stops on access/rate-limit
  errors without retry. A live one-page contract request returned 200 and
  1,969,765 HTML bytes. It was retained locally, not added to the working
  corpus.
- Against that retained full *The Dark Knight* response, the parser found 71
  prose passages across 24 section paths (revision `1383150687`, QID
  `Q163872`). This validates extraction mechanics, not completeness or
  narrative accuracy. The compact attributed fixture and ten pure parser
  tests are in Git; the large capture is not.
- Verification: **10 parser unit tests passed**; the isolated Docker/API/
  PostgreSQL suite passed **74 tests, 252 deselected** in `cinegraph_test`,
  with two third-party warnings. No working-corpus rows or vectors were
  changed. The historical six missing Wikidata snapshot files remain missing.
- Next: test revision-selection/source-use policy, resolve the named metadata
  gaps, then run the approved ten-film intake in isolation and audit every
  identity → snapshot → assertion/passage → rights/review → evidence/index
  outcome before touching the working corpus or expanding to 100/1,000.

### Follow-up — parser selection and exact structured-source capture (5 November 2026)

- The HTML capture adapter now has an explicit current-extraction mapping, and
  the isolated PostgreSQL test covers coexisting approved and experimental
  extraction versions.
- The Wikidata EntityData client now reads and hashes current robots.txt,
  applies RFC 9309 Allow/Disallow specificity, checks redirects, and retains
  exact upstream JSON bytes. A manual check fetched robots plus one Q163872
  response (revision `2564648138`, 290,568 bytes) at one-second pacing. The
  bytes stayed in memory; this did not change the corpus.
- The focused robots/URL tests and passage-selection tests pass; the subsequent
  full isolated Docker/API/PostgreSQL suite passed **79 tests, 252 deselected**
  in `cinegraph_test`.
- A direct import check exposed and fixed the resolver's missing
  EntityData-backed `fetch_entities` symbol. Ingestion now requires exact
  retained upstream bytes and commits each item before the next network fetch;
  it no longer reserializes parsed entities as though they were source
  responses. The old missing historical snapshots remain unresolved; current
  captures are not substitutes for those historical bytes.
- No title batch was captured or added to the working catalog. Next gate is
  verify the frozen ten-title QID and English sitelink evidence, then run the
  ten-film isolated intake and per-film source/evidence audit before any
  working-corpus expansion.

### Follow-up — ten-title source audit and compliant admin identity path (5 November 2026)

- The frozen first ten now have verified QID/title/year/type/sitelink mappings
  and exact English Wikipedia article snapshots in the ignored local pilot
  area. The integrity audit passed 10/10 and replayed all extraction output
  from retained source bytes. It produced 496 sectioned passages; 426 (85.9%)
  contain citation markers, with no exact duplicate passage text. Marker
  presence is not yet a resolved citation target or quality judgment.
- Captured passages cover plot and production/casting for all ten titles. This
  is still a capture/extraction result only: no operational catalog ingestion,
  passage-level source-link normalization, rights eligibility review, chunk or
  embedding build, paired retrieval evaluation, or 100-title expansion has
  been completed.
- The legacy admin worker was still making IMDb-to-QID requests through WDQS
  `/sparql`. All live query clients now fail closed on that disallowed route;
  the Indian candidate selector may read an already retained local cache but
  cannot make a new query request. Admin intake now captures a robots-checked
  ordinary English Wikipedia article page from the selected local title (or
  a validated, single-film `/wiki/{title}` override supplied by the operator),
  extracts its QID, fetches only that known QID through the exact-byte
  EntityData adapter, and requires article-QID, film type, selected year,
  title/alias, and IMDb P345 agreement before profile creation. The same
  captured article bytes are persisted after identity verification rather
  than fetched a second time.
- The local intake UI sends `x-operator-email`, while the API previously
  required an unrelated bearer token. These now agree on the configured
  operator email in `development`/`local` only. This is a local pilot gate,
  **not authentication**; the API returns unavailable for email-only access
  outside local development. Do not expose this mode publicly; production
  login/authorization remains a prerequisite.
- Verification: **29 focused pure tests passed**, **265 non-integration tests
  passed**, and the isolated Docker/API/PostgreSQL suite passed **81 tests,
  265 deselected** against `cinegraph_test` (two third-party warnings). The
  new persistence integration test confirmed exact HTML bytes, revision and
  source assertions. A fresh live admin-path probe could not run from the host
  because DNS resolution to Wikimedia failed; the previously captured local
  ten-title artifacts remain available, but the new title-derived flow still
  needs a manual live contract run before production use.
- The next gate is review of ten-film evidence and rights/attribution state,
  followed by versioned chunking, isolated embeddings and frozen paired
  retrieval evaluation. The 100-film run remains gated on those results.

### Follow-up — passage citation targets resolved offline (5 November 2026)

- Added an offline audit that maps retained citation markers to in-article
  reference-list entries and records external reference URLs without copying
  bibliography text. The first run exposed that the v1 parser mistook 28
  page-number superscripts on *Inception* for citations. The parser now accepts
  only reference superscripts whose IDs use the article citation-marker form;
  this is extraction v2. The original v1 derivatives remain untouched, and the
  new content-addressed v2 derivatives have their own manifest and audit.
- The corrected v2 run still yields 496 passages, with 426 containing one or
  more citation markers. All 2,610 marker occurrences map to an in-article
  reference-list entry. Of those, 1,655 (63.4%) have at least one external
  reference URL; 955 do not have an external URL through this method, which
  includes valid print/bibliographic references. Only 155 cited passages have
  every marker linked to an external URL. These are locator-coverage counts,
  not a broken-reference rate, source-quality score, or entailment judgment.
  The per-passage map and title breakdown remain in the ignored local
  `citation-target-audit.json` and `.md` outputs.
- These links are locators, not support verification, source-quality review,
  or reuse permission. Wikipedia prose remains CC BY-SA 4.0; each linked source
  has its own terms. Do not index or display external-source text until its
  asset-specific rights and attribution are established.
- CC BY-SA 4.0 itself is not a non-commercial license: it permits commercial
  sharing and adaptations provided attribution, change-notice, ShareAlike and
  no-additional-restrictions terms are met ([license deed](https://creativecommons.org/licenses/by-sa/4.0/deed.en)).
  Whether CineGraph's particular chunking, embedding and generated comparison
  outputs are adaptations, and how ShareAlike applies to the paid product, is
  not settled by this data audit; get legal review before public monetized use.
- Verification: 23 focused source-capture/parser/citation tests passed; the
  full non-integration suite passed **270 tests**, and the isolated Docker/API/
  PostgreSQL suite passed **81 tests, 270 deselected** against `cinegraph_test`
  (two third-party warnings). Re-extraction and both audits replay only
  retained source bytes; they used no network and wrote no raw prose to Git.
  No retrieval, chunking, or embeddings have been produced for this pilot.
- Next: review a stratified sample of passage-to-reference mappings for
  correctness, classify source/use rights and attribution, then build only an
  isolated eligible-evidence chunk/retrieval experiment. Keep the 100-film
  expansion gated on measured paired-question results.

### Follow-up — citation-position extraction and current ten-film baseline (5 November 2026)

- A stricter audit found bibliography-derived text leaking from a `Sources`
  section and citation markers captured from image captions and standalone
  quote attributions. The parser now excludes bibliography/source headings
  and thumbnail/gallery captions, and derives the passage marker set from the
  retained marker positions. Every marker position records a passage-local
  paragraph index and character offset. The failed v3-v5 derivatives remain
  immutable local artifacts; current output is separately versioned as parser
  v6 under `snapshots/wikipedia-passages-v6/`.
- The v6 extraction/integrity audit passes 10/10 captured articles and replays
  **484 passages** from the retained source bytes. The citation audit reports
  **2,612/2,612** marker occurrences linked to an in-article reference-list
  entry; **1,656/2,612 (63.4%)** have an external URL. **956** have no external
  URL through this method, and 155 cited passages have all markers URL-linked.
  Removing 12 bibliography/source passages is why the total is lower than the
  historical 496-passage v2 result. The counts measure linkage only—not whether
  a source supports the passage, source quality, legal eligibility, or reuse
  permission. The full passage-to-reference map remains local and ignored.
- Verification after this parser change: **15 focused parser/re-extraction/
  citation tests passed**, **284 non-integration tests passed** (50 skipped),
  and the isolated PostgreSQL/API suite passed **81 tests, 270 deselected** in
  `cinegraph_test`. No model download, corpus write, or embedding run occurred.
- The detailed execution baseline is maintained in
  [`catalog-data-roadmap-v2.md`](catalog-data-roadmap-v2.md): source roles and
  rights gates, target record/evidence model, resumable ingestion pipeline,
  phased 10 → 100 → 1,000 expansion gates, retrieval evaluation, and
  decisions for additional datasets. This ten-title audit does **not** satisfy
  those gates: citation support/rights review, eligible chunking, embeddings,
  and paired retrieval evaluation remain pending.
- Next: manually review a stratified ten-film sample using each citation's
  paragraph/offset and target; separately inspect passage boundaries and
  attribution/rights. Only after that should eligible text enter an isolated,
  versioned retrieval experiment. Keep raw captures and derivatives local.

### Follow-up — first citation-support spot check (5 November 2026)

- Reviewed one deterministic citation-bearing paragraph per title against its
  retained local reference entry and the exact target where accessible. Two
  sampled narrow statements were directly supported, one was partial, one
  exposed a current link/edition mismatch, and six remain unverified. This is
  a convenience smoke sample, not an accuracy estimate; inaccessible targets
  are unknown, not false. The per-title labels stay in the ignored local file
  `data/evaluation/catalog-intake/first10-v1/citation-support-review-v1.md`.
- The spot check confirms we cannot use a Wikipedia citation marker or URL as
  an automatic support signal. Keep external-reference prose out of the local
  product evidence unless its separate rights/access terms are cleared. The
  current Wikipedia passages retain their own snapshot/revision and CC BY-SA
  provenance; public monetized use still needs the attribution/ShareAlike
  implementation and legal review already noted above.
- This partially advances, but does not complete, the Phase 2 review gate.
  Next: a passage-boundary and narrative-coverage sample; then an isolated
  local retrieval evaluation over the eligible, revision-pinned Wikipedia
  evidence. Keep supportability labels and source snapshots local, and do not
  expand to 100 until retrieval quality is measured on the frozen questions.

### Follow-up — exact-target citation checks (6 November 2026)

- A targeted second pass used the retained v6 marker offsets to inspect exact
  claims at BFI, the Vatican, Vulture, and RCDB. Four narrow factual details
  were directly supported; an AllMovie summary explicitly attributed its text
  to Wikipedia and therefore did not count as independent corroboration. The
  old 12 Angry Men Variety scan remained inaccessible; a different AFI catalog
  page was not substituted for it. Local dispositions are in the ignored
  `citation-support-review-v2.md`.
- This was purposive follow-up, not a representative accuracy sample. No
  corpus, embedding, or operational-fact changes were made. Citation linkage,
  claim support, independent corroboration, target accessibility, and reuse
  rights remain separately reviewed. Continue with a declared balanced sample
  and rights analysis before the isolated retrieval experiment; the 100-title
  expansion gate remains closed.

### Follow-up — section-balanced ten-film citation sample (6 November 2026)

- Froze a deterministic selection of 20 citation markers from the retained v6
  source map before opening the targets: one Story/Production/Cast and one
  Interpretation/Reception marker for each film. The sample spans 17 publisher
  domains (three appear twice), so it is balanced by title and broad section,
  not a probability sample or a fully unique-source sample.
- Exact-target review yielded 4 narrowly supported claims, 3 partial claims,
  and 13 unresolved/unverified claims. It surfaced the distinctions we need
  in the pipeline: direct metadata/credit support; first-person testimony;
  attributed critical opinion; stale/historical ranking links; and inaccessible
  targets. The exact sample manifest, citations, and dispositions remain in
  ignored `data/evaluation/catalog-intake/first10-v1/citation-support-review-v3.md`.
- No linked-source prose was copied into the corpus, and no operational facts,
  chunks, embeddings, or working-database rows changed. The audit remains too
  small and access-biased to justify a support-rate claim. Continue with a
  separate source-rights / attribution matrix and the isolated, rights-eligible
  retrieval evaluation; the 100-film expansion is still gated.

### Follow-up — intended-use rights gate (6 November 2026)

- Checked the official Wikimedia/Wikidata, TMDB and IMDb reuse terms and
  documented a source-by-purpose matrix in `catalog-data-roadmap-v2.md`.
  Accessibility, an API key, and an article citation are not blanket permission
  for every downstream use.
- Code review found narrative chunking previously treated CC BY-SA plus an
  attribution URL as sufficient for semantic indexing, while retrieval queried
  all eligible chunks without checking the source's intended-use state.
- Added a conservative, explicit `semantic_use_approved` gate: new chunk
  creation, embedding cache/index inputs, vector reuse, and both lexical/vector
  retrieval require it. Structured metadata display policy remains separate.
  Wikipedia currently remains
  `attributed_reuse`, so its narrative content is retained and source-linkable
  but does not enter new retrieval runs unless a reviewed approval is recorded.
- An isolated real-PostgreSQL test now verifies default-deny chunking and
  retrieval, then opt-in with an explicit test fixture approval. Pure policy
  tests cover the distinction. No working corpus rows, raw snapshots, vectors,
  or local evaluation artifacts were changed.
- This is a conservative product-policy gate, not a legal conclusion about
  CC BY-SA embeddings or generated text. The final paid/public use model still
  needs qualified review and a versioned per-asset/use rights record; the
  100-film expansion remains gated.

### Follow-up — ten-film structured-field coverage and dataset-admission plan (5 November 2026)

- Extended the offline capture audit to report structured Wikidata field
  presence, statement counts, release-date precision/references, and cast
  character qualifiers. The retained pilot snapshots contain 10/10 titles
  with at least one release date, runtime, country, original language, genre,
  director, cast, screenwriter, producer, cinematographer, and editor value;
  music is present for 9/10, production company for 9/10. This describes the
  captured EntityData only—it is not a correctness, completeness, rights, or
  app/API projection result.
- Across ten captured works there are 51 release-date statements: 48 day-, 2
  month-, and 1 year-precision; 49 have a territory qualifier and 38 have a
  Wikidata statement reference. There are 13 runtime statements, 12 with
  references. These are multiple source-scoped events/values; do not collapse
  them into a single date/runtime without a selection policy and edition or
  territory context.
- The 328 cast statements include a character entity (P453) on 136, a
  character-name string (P4633) on 169, and one of those qualifiers on 214
  (65.2%); 114 have neither. Coverage varies by film, so “cast present” does
  not mean actor-to-character coverage is adequate. The local capture is not
  ingested into the working catalog. The raw Wikidata capture adapter retains
  property statements and qualifiers, but this pilot does not yet verify a
  reviewed operational projector or the exact film-profile display for these
  fields. That projection is a required gate, not something to infer from
  source presence.
- Passage audit: 484 v6 passages, 426 with citation markers, no exact duplicate
  text, and 2 passages longer than 2,500 characters. Do not simply truncate
  long passages: the next chunker must preserve section, citation marker
  offsets, source revision, rights state and sentence boundaries; oversized
  indivisible spans should be excluded/reported rather than silently clipped.
- Dataset onboarding decision: keep each dataset/source in its own field-level
  provenance lane. First produce a local manifest of candidate dataset version,
  license/terms, permitted storage and commercial display/embedding scope,
  attribution, stable identifiers, fields, language/territory semantics, and
  update cadence. Then map fields to the existing work/release-event/person/
  credit/assertion/passage model. Do not bulk import solely because a dataset
  is large or publicly downloadable. IMDb files stay local and restricted to
  the use allowed by their terms; Wikidata CC0 structured values and Wikipedia
  CC BY-SA prose remain separate assets with distinct attribution/use rules.
- Planned sequence for incoming data is now explicit: (1) retain the exact
  source/version and rights decision; (2) resolve work identity to the frozen
  pilot without auto-merging; (3) compare field definitions and retain raw
  values/qualifiers; (4) run a 10-record adapter fixture with duplicate,
  conflict, missing-field and role/date-precision cases; (5) project only
  eligible reviewed facts, with provenance visible through API and UI; (6)
  compare per-field coverage and sampled correctness against the Phase 0
  baseline; (7) run the isolated eligible-passage retrieval benchmark; only
  then permit checkpointed expansion to 100 and 1,000. Each stage produces a
  versioned manifest and human-readable coverage report.
- Verification for this audit change: 9 focused capture-audit tests pass; the
  full non-integration suite passes **285 tests** (50 skipped, two third-party
  warnings); the local v6 audit replays 10/10 films and 484 passages. The
  updated numbers are written to the ignored local `capture-audit.md`; no
  corpus rows, snapshots, or vectors were modified. The separate isolated
  PostgreSQL/API suite was not rerun because this change only alters the
  offline capture report and pure audit tests.

### Follow-up — extraction version gate corrected and citation positions persisted (5 November 2026)

- Found a concrete mismatch: the live HTML intake was extracting parser v6,
  while the current-passage read rule still preferred a historical v1
  extraction. Newly ingested passages could therefore be treated as missing
  by reads and the intake worker's plot-evidence check. The selector now uses
  explicit version precedence and the production extraction is v7, which
  changes the stored derivative contract without changing parser v6 output.
- Added an additive migration for `citation_positions` on narrative passages
  and evidence chunks. HTML extraction stores marker ID, passage paragraph
  index, and source-relative character offset. The versioned chunker v5 maps
  positions to the sentence spans carried by each chunk, includes position
  data in run identity, and writes those locators alongside the chunk. It does
  not alter immutable passage text or turn citation locators into support
  labels.
- Real `cinegraph_test` integration now exercises capture snapshot → v7 passage
  → current-passage selector → citation-preserving chunk. It also verifies
  legacy-v1 fallback and that unrelated experimental extractions remain hidden.
  The migration and full isolated API/PostgreSQL suite passed: **81 passed,
  272 deselected**. The full non-integration suite passed **286 tests** (50
  skipped, two third-party warnings); focused pure tests passed **26**,
  including deterministic chunk citation attribution. No working-corpus rows
  or vectors were changed.
- Remaining Phase 2 gates: broader stratified passage/support review, rights
  and attribution assessment, and paired question-led retrieval evaluation.
  The ten-film capture remains isolated; no expansion to 100 follows from
  these integrity tests alone.

### Follow-up — rerun citation audit and isolate integration-test failure (5 November 2026)

- Replayed the local capture-bundle audit without network access: **10/10**
  selected films pass identity/capture integrity with **484** extracted
  passages. Replayed citation-target resolution: all **2,612/2,612** citation
  marker occurrences resolve to a retained reference-list entry; **1,656**
  (63.4%) have an external URL, and only **155/426** cited passages have URLs
  for every marker. These are locator-resolution results, not proof that the
  cited source supports the text. The earlier manual check remains only 2
  narrowly supported samples, 1 partial, 1 edition mismatch, and 6
  unverified; it is not a general accuracy estimate.
- Re-extracted all ten retained HTML snapshots using the deterministic parser
  and verified the versioned derivative against the source hashes and pinned
  revisions: **10/10**, **484 passages**, **2,612 citation positions**, zero
  exact duplicate passages. This offline derivative audit reports parser v6;
  it does not replace the database integration check for the operational v7
  stored-passage selection and read path.
- An additional offline structural check on the ten v6 derivatives found
  **0 invalid positions among 2,612**: each marker belonged to its passage's
  marker list and its offset lay within the indicated paragraph. This checks
  coordinate bounds only; it does not establish sentence-level attribution or
  support from the referenced source. The check is now part of the replayable
  pilot audit; two focused tests pass, including a misplaced-offset rejection.
- Focused deterministic tests for passage-version selection, citation-aware
  chunking, HTML extraction and pilot re-extraction pass: **18 passed, 1
  skipped**. The broader non-integration suite passes **272 tests**, with 81
  integration tests deselected and two third-party warnings. `git diff
  --check` also passes.
- The first isolated PostgreSQL/API rerun exhausted host disk: pytest could
  not create temporary/cache files and the test DB connection was refused,
  producing cascading failures. After removing only the ignored,
  regenerable `frontend/.next` build cache (190 MB; no local web server was
  listening), available host space rose from 116 MB to 417 MB, but a second
  Docker test-runner invocation remained stalled during `docker compose up`
  before reaching its health check and had to be stopped. The latest
  `has_plot` integration assertion is therefore **not verified**. Do not
  treat the earlier 81-test run as verification of
  that newest assertion.
- No working-corpus rows, raw snapshots, model weights or embeddings were
  changed. The capture and citation audits write only ignored local reports.
  Next: restore a healthy dedicated Docker test stack with adequate disk
  headroom, verify the new integration assertion, then continue the
  stratified passage/support and rights review before any 100-film expansion.

### Follow-up — isolated database gate restored (5 November 2026)

- Docker became responsive after the earlier interruption. The existing
  `cinegraph_test` PostgreSQL volume completed crash recovery without deletion
  or recreation; migrations and the isolated API then started successfully.
- The current integration suite passed **81 tests**, with **272 deselected**
  and two third-party warnings. This run includes the new `has_plot` assertion
  for the v7 article passage path and supersedes the failed disk-pressure run
  described above. The broader non-integration suite previously passed 272.
- This verifies the test-stack path, not a ten-film working-corpus ingestion,
  rights clearance, or retrieval quality. Continue the ten-film review and
  question-conditioned evaluation before expanding the selected collection.

### Follow-up — ten retained articles replayed into the isolated database

- An explicitly opt-in integration test replays all ten retained article
  snapshots, verifies their hashes, QIDs and revisions, and stores them in a
  fresh schema inside `cinegraph_test`. All ten replayed successfully:
  **484 current v7 passages**, plot present for each film, and zero new
  passages on a second extraction. The test passed without external requests.
- This validates the retained Wikipedia snapshot-to-passage read path; it
  does not verify structured Wikidata projection, chunking for the entire
  pilot, rights approval, writer-question relevance, or working-catalog
  publication. Those gates remain open.

### Follow-up — ten-film chunk replay

- Extended the opt-in isolated replay through the versioned chunker. All 484
  passages were selected; it produced **500 chunks**, of which **496** passed
  the configured minimum-word check and four were excluded as too short.
  Each of the ten films had eligible chunks. A second run reused the existing
  chunks without creating new rows. Every stored chunk was checked against its
  source passage and its citation positions were a subset of that passage's.
- **440 chunks** carry citation positions; the stored total is 2,648 because
  overlapping chunks may repeat positions. This is not 2,648 independent
  citations and does not prove citation support or retrieval relevance. The
  integration test passed with two third-party warnings (including a local
  PyTorch/NumPy compatibility warning). It remains isolated from the working
  catalog; structured projection and question-led evaluation are still open.

### Follow-up — ten-film Wikidata projection replay

- Replayed all ten retained Wikidata EntityData responses alongside the
  article replay in a fresh `cinegraph_test` schema. The projector scanned
  **3,276** source statements, created **1,303** evidence-linked operational
  assertions, and left **1,973** unsupported properties unprojected. Raw
  source statements remain retained; unsupported does not mean false.
- A second projection created no new assertions. The test checked that every
  created assertion had a source-assertion evidence link and retained the
  source qualifiers. It passed with two third-party warnings. These figures do
  not measure field correctness, actor-to-character UI display, review status
  quality, or readiness for publication. The working catalog was not changed.

### Follow-up — user-facing structured metadata audit

- In the isolated ten-film replay with only the retained Wikidata and
  Wikipedia inputs, the film read model returned a release year for **10/10**
  films, but the sourced-credit reader returned credits and character names
  for **0/10**. This is a read-model/source representation gap, not a claim
  that the working catalog lacks other sources.
- Wikidata's projected cast assertions point to person entities and retain
  character qualifiers; the sourced-credit reader expects a named credit in
  `value_json`. The pilot has not captured person/character labels, so QID
  placeholders cannot safely be shown as names. Do not infer roles or treat
  qualifier presence as display-ready coverage. Resolve explicitly sourced
  labels or use eligible attributed credits, then verify the API and film
  page. Release-year presence does not validate territory or exact date.

### Follow-up — local-only named-credit path

- Tested the retained Wikidata IMDb identifiers against the local IMDb index
  for the ten pilot films, checking the selected year and replaying each bundle
  into a fresh `cinegraph_test` schema. The existing credit projector and
  reader returned at least one actor-to-character credit for **10/10** when
  `include_noncommercial=True`; the default reader excluded these credits for
  all ten. The integration test passed with two third-party warnings.
- This establishes an attributable local-research path, not independent
  verification of every credit or a commercially cleared solution. It does
  not change the working catalog or automatically expose restricted content.
  Film-page/API verification, eligible public-source credits, and a safe
  production rights policy remain necessary.

### Follow-up — source-backed Wikidata labels

- EntityData extraction now retains a present English label as a distinct
  `labels.en` source assertion linked to the exact snapshot; it never turns a
  QID fallback into a name. Replaying a retained snapshot can append this new
  source field without overwriting original bytes or earlier statements.
- The focused raw-data and ten-film isolated integration tests pass: **12
  passed**, with two third-party warnings. This adds a provenance primitive,
  not actor-name coverage: person/character EntityData still must be captured
  under policy and resolved before the credit reader can safely use it.

### Follow-up — source-linked credit-label canary

- From the retained *The Dark Knight* cast statement, selected actor Q45772
  and its P453 character Q78607187. Two sequential EntityData requests passed
  the robots check; the captured English labels are Christian Bale and Bruce
  Wayne. Exact responses, hashes, revisions and capture times remain in an
  ignored local canary bundle. No working-catalog data was changed.
- An opt-in `cinegraph_test` replay verified the film's cast statement and
  character qualifier point to those QIDs and that each retained entity label
  is a source assertion. The test passed with two third-party warnings. This
  is one provenance canary, not a field-accuracy estimate or a working film
  page: the credit read model still does not consume these label assertions.

### Follow-up — source-backed Wikidata credit read model

- The credit reader now batches Wikidata target-label lookups and uses only
  English label assertions from the latest retained successful CC0 snapshot.
  A cast character is displayed only for an unambiguous P453 QID with its own
  retained label; missing or conflicting labels are not guessed. API credit
  responses now carry separate actor and character label source URLs and
  revisions as well as the film-credit source.
- In the isolated canary, the reader returns Christian Bale as Bruce Wayne;
  before the actor capture it returns no such named credit, and with only the
  actor capture it leaves the character empty. Five focused tests pass with
  two third-party warnings. This does not populate the working catalog or
  validate the film page; broader person-label acquisition, per-field review,
  UI provenance display, and API/browser testing remain open.

### Follow-up — reproducible credit-label candidate manifest

- Added an offline, immutable manifest builder that validates each retained
  film snapshot's hash, revision and identity state, then records deduplicated
  person and explicit P453 character QIDs with their source statement and
  qualifier locators. It reports malformed targets and skips deprecated
  statements; it makes no requests and publishes no facts.
- The ten-film bundle yields **445 unique targets**: 308 appear as cast,
  119 as characters, 17 as writers and 8 as directors (roles can overlap).
  There are **zero reported malformed target links** in this sample. Two
  focused tests pass, including snapshot-hash rejection, and replay produces
  the same immutable manifest. Counts describe candidates—not captured
  labels, reviewed identities, or display-ready credits. The local manifest
  remains ignored; acquisition and policy/quality gates are still required.

### Follow-up — non-commercial display boundary

- Configuration now rejects `serve_noncommercial_sources=true` unless the
  environment is explicitly `local` or `development`; six configuration
  cases and three source-credit policy tests pass. This prevents a declared
  production or staging configuration from silently enabling the local IMDb
  display path.
- This is not an authentication or deployment boundary: the current default
  environment is `development`, and a publicly exposed development instance
  could still serve restricted data. Deployment must explicitly set a
  non-development environment, disable the flag, bind appropriately, and
  review source rights before release.

### Follow-up — full ten-film Wikidata credit-label capture and replay

- The resumable, sequential, robots-checked EntityData job completed all **445
  of 445** targets from the retained ten-film manifest. Its offline audit
  verified every snapshot hash, QID, source revision and source URL; all
  captures record the same robots.txt digest. The local raw snapshot bundle is
  **27,449,229 bytes** and is ignored by Git. The audit reports 440 English
  labels and 5 entities without an English label; those five stay unresolved.
- Added an offline bundle audit command and a label-only source persistence
  path. It stores the exact EntityData snapshot and only the `labels.en`
  `SourceAssertion`, avoiding accidental ingestion of unrelated person claims.
  The admin intake worker now selects explicit people and P453 character QIDs,
  reuses retained snapshots, backfills a missing label assertion from exact
  bytes, and fetches only targets without a retained snapshot. New requests
  remain sequential, robots-checked and committed before the next request.
  The isolated replay imported all captures into a fresh schema inside
  `cinegraph_test`; two labels were already present from the canary, so replay
  added 438 new label assertions and found 440 total. Replaying one capture
  again created no new snapshot or label assertion; the worker's all-retained
  path reused 445 snapshots without making another request.
- The ten-film read model now has named cast for **10/10** and at least one
  sourced actor-to-character credit for **10/10**. A bounded display-order
  correction prioritizes credits with a sourced character name, so the 20-item
  per-source cap no longer hides those useful pairs. The retained pilot still
  projects 1,303 operational assertions from 3,283 statements; it creates 500
  evidence chunks from 484 eligible passages, covering all ten films. These
  are coverage and pipeline results, not full correctness or rights approval.
- Verification: the explicit local PostgreSQL pilot replay passed; the focused
  offline manifest/checkpoint/audit/credit policy suite passed **12 tests**;
  the full non-integration regression suite passed **288 tests** (82
  integration tests deselected).
  The working corpus was not changed. UI provenance display, film-page/API
  browser checks and independent per-credit review remain open.

### Follow-up — credit provenance is visible and tested end to end

- The film profile now separates three links for an attributed actor/role:
  the film's credit statement, the actor's source label, and (when present)
  the character's source label. The UI does not make a name-label URL appear
  to be evidence for the actor-to-character relationship.
- The isolated integration fixture uses a field-minimized *The Dark Knight*
  Wikidata excerpt, tied to the original capture hashes/revisions and carrying
  the exact captured P161 statement ID and P453 Joker qualifier. English label
  assertions follow the production adapter's normalized representation. Full
  EntityData bytes remain local; the fixture is CC0 and is seeded only into
  `cinegraph_test`. It does not change the working catalog. A real HTTP/API
  assertion verifies the statement and distinct label URLs/revisions. A
  Playwright test checks the rendered links. An offline cross-check against
  the three full local snapshots confirmed each source hash, byte size,
  revision and English label, and confirmed the fixture's actor value and
  character qualifier exactly match the captured P161 statement.
- Verification after fixture reseed: backend integration suite **82 passed,
  1 skipped, 288 deselected**; frontend production build succeeded; Playwright
  **7 passed** against the isolated API. The first browser attempt exposed that
  the character-name link pointed at the label rather than the credit
  statement; that was corrected and all browser tests then passed.
- A separate local-only boundary sample checked 30 deterministic v6 passages
  (Plot and Production for all ten films plus one alternating contextual
  section per film) against the original retained HTML. An independent HTML
  parser reconstructed each full heading path and compared each passage
  paragraph with a complete source paragraph/list/blockquote: **30/30 matched,
  0 failed**. The local method/results are in ignored
  `data/evaluation/catalog-intake/first10-v1/passage-boundary-review-v1.md`.
- These checks verify provenance plumbing and page behavior, not the
  correctness/completeness of every displayed credit. The boundary sample is
  not corpus-wide parser approval, semantic correctness, reference support, or
  a reuse-rights decision. Independent per-credit review, broader source
  support and rights decisions, and the frozen question-led retrieval
  evaluation are still required before the next catalog expansion gate.

### Follow-up — snapshot-scoped narrative-use review

- Replaced the source-wide semantic-use gate with an append-only
  `NarrativeUseDecision` ledger keyed by immutable snapshot, purpose and
  decision version. A database trigger rejects updates/deletes, and a database
  constraint requires an approval basis URL and rationale. Ingestion
  chunking, the offline RAG-corpus exporter, and every embedding/retrieval/
  model-input query require the latest decision to be explicitly approved; no
  pre-existing source-wide flag is migrated into an implicit approval. Changing
  the decision changes the preprocessing manifest, and a later denial removes
  already-created chunks
  from eligible retrieval without destroying their lineage.
- Added a local review queue showing source/revision/license/hash, linked film
  labels, section samples and the latest decision. Approval requires a retained
  attribution URL, an HTTPS basis URL and an operator rationale; the interface
  explicitly says this is a recorded operator decision, not legal advice.
  Decisions can be revised only by appending a new version.
- The default catalog's existing Wikipedia snapshots have no new per-snapshot
  approvals, so this change deliberately excludes them from semantic use until
  reviewed in the local operator desk. This is a safety/rights workflow, not a
  content-quality or product-readiness claim.
- Verification: focused policy/preprocessing tests **14 passed**; full offline
  regression suite **289 passed**; isolated PostgreSQL/API integration suite
  **86 passed, 1 skipped**; frontend production build succeeded; Playwright
  **8 passed**. The integration checks cover schema migration, review queue,
  authorization rejection, per-revision independence, versioning, database
  append-only enforcement and retrieval revocation. Raw data, vectors and the
  working corpus were not changed. This milestone does not complete the
  catalog plan: source/field quality, broader rights review, retrieval quality
  evaluation and the 100/1,000-title expansion gates remain open.

### Follow-up — rights-aware catalog readiness measurement

- Upgraded the read-only catalog report to count distinct narrative snapshots
  and report how many have license/attribution metadata, a latest decision,
  approval, denial, or remain eligible under the same per-snapshot policy as
  retrieval. Existing stored vectors and vectors eligible for current semantic
  use are now reported separately, so revocation cannot be hidden by historical
  index counts.
- Added a deterministic policy test covering unreviewed, denied, approved and
  restricted-license snapshots. It passes. Python compilation and whitespace
  checks pass. At first the local Docker stack was stopped, so the full report
  was deferred until the existing database could be started and safely audited.
- After this code-level test, started only the existing local PostgreSQL
  container and verified the working database was at Alembic `20261005_15`.
  Applied the reviewed additive migrations through `20261106_20`; no source,
  passage, chunk or vector rows were modified. The local rights ledger is
  present and empty. A subsequent read-only report over all **2,586** films
  found **3,037** distinct film-linked narrative snapshots, all with recorded
  license/attribution fields, **0** decisions and therefore **0** semantically
  eligible snapshots or vectors. There are **48,352** historically stored
  vectors; these are not currently available to retrieval under the policy.
  The report also identifies Plot for 1,472 films, Production for 1,290 and
  Reception for 1,460 using section-heading heuristics only. Local output is
  ignored at `data/evaluation/catalog-readiness-v6.json`; these are coverage
  counts, not correctness or commercial-rights determinations.
- Fixed the report output-root check to resolve relative to the project, and
  made it fail closed on older schemas by recording the missing ledger and
  returning zero eligible vectors rather than querying a nonexistent table.
  This was exercised first against the pre-migration schema and then against
  the migrated local database.
- The production Next build and frontend unit tests pass after the admin proxy
  fix. The local Docker API is healthy, and `GET /admin/rights` plus the
  proxied rights queue both returned HTTP 200 using the configured operator
  email. This exposed a dead `ADMIN_INTAKE_TOKEN` requirement in both admin
  proxies: Compose does not configure that token and the API does not validate
  its bearer value. Removed the unused check/header while retaining local-mode,
  loopback-bind and exact operator-email checks at the proxy and API. This is
  explicitly local-only, not production authentication. Docker frontend image
  build was separately blocked by a Docker Hub `node:22-alpine` metadata
  timeout; local Next build succeeded instead.
- Extended the rights queue with a total count, bounded offset pagination and
  deterministic ordering, and added previous/next controls so the operator
  can reach beyond the first 100 snapshots. A real PostgreSQL API test verifies
  two pages contain every snapshot exactly once. Verification: full non-
  integration suite **290 passed**; focused PostgreSQL paging test **1 passed**;
  full isolated API integration suite **86 passed, 1 skipped**; frontend unit
  suite **5 passed**; Next production build succeeded; Playwright **8 passed**.
  The integration stack retained its non-local admin denial check. No new
  source approvals were made. The local live queue totals **3,039** snapshots:
  **3,037** linked to film records plus **2** narrative snapshots without a
  Film link. API reads returned 100 items at both offsets 0 and 100.

### Follow-up — snapshot integrity audits across local mount namespaces

- A read-only integrity check run inside Docker treated host `file://` URIs as
  missing when their original absolute paths were not visible inside the
  container. That status conflated actual absence with an audit process that
  lacked the corresponding mount.
- Added opt-in `--path-map PERSISTED_ROOT=VISIBLE_ROOT` support to the integrity
  auditor. It resolves mapped paths only for that audit, verifies bytes by
  SHA-256 and size as before, reports unmatched URIs as `unmapped`, and still
  reports `missing` when the translated path is visible but absent. It never
  rewrites snapshot URIs or changes snapshot recovery/ingestion behavior.
  Mappings are component-bounded and reject path traversal.
- The offline capture and citation audits were replayed against the retained
  first-ten bundle: **10/10** film captures, **484** passages, **2,612/2,612**
  markers linked to a retained reference entry, and **1,656** markers with an
  external URL. The credit-label audit verified **445/445** captures, with
  **440** English labels and **5** unresolved no-English-label entities.
- Verification for the path-mapping change: the full offline backend suite
  passed (**294 passed, 88 integration tests deselected**), including all four
  pure snapshot-integrity tests; Python compilation and `git diff --check`
  passed. The Conda environment needed the existing local
  `data/vendor/mwparserfromhell` fallback on `PYTHONPATH`. PostgreSQL
  integration then passed (**87 passed, 1 skipped**) against `cinegraph_test`;
  this includes the snapshot-auditor case, which created and used an isolated
  schema. The read-only mapped-path audit over the working database verified
  4,467 Crossref, 1,488 IMDb, 544 OpenAlex and 518 TMDb snapshots. It classified
  1,000 English Wikipedia and 905 Wikidata snapshots as `unmapped`; their
  recorded URIs point under `/private/tmp`, outside the explicit project and
  container roots. This does not establish whether those files still exist on
  the host, and they were not inspected. The report found no `missing`, hash-
  mismatch or size-mismatch files among the mapped roots. No working-corpus
  data, source snapshots, or evaluation artifacts were changed. The next gate
  remains rights/support review and question-conditioned retrieval evaluation;
  no rights decisions or 100-film expansion were made.

### Follow-up — retain and display scoped runtime evidence

- The earlier runtime policy correctly refused to pick a scalar when eligible
  source assertions differed or carried qualifiers, but the film page reduced
  that evidence to “disputed” and hid the values that could explain the
  difference. The API now returns admissible runtime options with their
  converted minute value, bounds, typed qualifier property/entity IDs, source,
  revision, review state, license and rights status. The conservative scalar
  remains unset whenever version/value ambiguity remains; no source wins by
  list order.
- The film page now distinguishes multiple reported values, version-scoped
  runtimes, approximate bounds and unresolved values. An expandable evidence
  list links each assertion back to its source and Wikidata qualifier IDs.
  Runtime variants remain evidence, not an inferred choice of theatrical,
  extended or otherwise preferred cut.
- Extended the write-once, read-only pilot metadata audit to include the exact
  displayable runtime options. The fresh local-only v8 audit reports 100 films,
  99 with at least one displayable option, 117 options total and 16 with
  version qualifiers. The existing profile audit still finds 17 films whose
  runtime requires review; exposing options does not resolve that review.
  Report: `data/evaluation/catalog-pilot-metadata-audit-v8.json` (ignored/local).
- Verification: offline backend suite **295 passed, 88 integration deselected**;
  isolated Docker/PostgreSQL/API integration suite **87 passed, 1 skipped** on
  `cinegraph_test`; the API assertion verifies the serialized runtime option,
  and its Playwright film-profile flow passed against that same test stack.
  Frontend unit suite **5 passed**; TypeScript check and Next.js production
  build succeeded; Python audit and whitespace checks passed. No corpus facts,
  snapshots, passages or vectors were edited. The
  broader 100-film quality, rights and enrichment gates remain open.

### Follow-up — filter the snapshot-scoped rights queue

- The local review desk previously paginated all narrative snapshots but could
  not narrow the queue to a film or its latest review state. Added server-side
  film-title and state filters (`unreviewed`, `approved`, `denied`,
  `review_required`), with counts and pagination scoped to the filtered result.
  Matching is literal (SQL wildcard characters in a title are escaped), and
  state is derived from the latest append-only decision for the semantic-model
  use case.
- Added responsive controls to the operator page and kept the review boundary
  intact: this change adds no approval, changes no source/license metadata, and
  does not index or embed any passage.
- The Playwright test server now supplies explicit loopback-only local-admin
  settings for its guarded proxy. The former browser failure was an unset
  test-server environment (503), not absent Dark Knight fixture data.
- Verification: focused real-PostgreSQL rights API integration assertions
  cover matching, empty results, literal wildcard handling, invalid states,
  and state transitions. Isolated API suite: **87 passed, 1 skipped** on
  `cinegraph_test`; complete Playwright suite: **10 passed**. These are test
  fixture results only; production/local-corpus rights decisions remain for
  the operator and legal review.
- A runtime audit found the already-running local API container was an older
  image that ignored the new filter parameters. Rebuilt and restarted only the
  API service with `--no-deps`; the working PostgreSQL service and volume were
  not changed. The live queue now reports **3,039 unreviewed**, **0 approved**,
  **0 denied** and **0 deferred** snapshots. The actual local Next app at
  `localhost:3001`, with explicit loopback-only admin settings, displays the
  full count and narrows *The Dark Knight Rises* to its two snapshots. This
  check did not write review decisions. Until an operator reviews eligible
  assets, no working-corpus narrative snapshot can enter semantic indexing.
- Rechecked the actual server-rendered *The Dark Knight Rises* profile against
  the local API: it displays the sourced 2012-07-20 release event rather than
  treating the legacy 2022-10-06 value as canonical, exposes the discrepancy,
  and renders available actor-to-character labels with source links. The
  profile still flags the runtime as needing version review. This is one-film
  verification, not a 100-film completeness claim.

### Follow-up — retain CC0 credit labels and show source-scoped credits

- A profile audit found that Wikidata retained cast statements but the actor
  and character target entities had no local English-label snapshots. This
  made those sourced credits invisible even though the underlying statements
  existed. Ran the existing rate-limited, policy-guarded label intake for the
  *The Dark Knight Rises* canary only: 66 target QIDs considered, 66 CC0
  snapshots retained, 64 source assertions added, and two targets had no
  English label. This adds raw source evidence only; it creates no reviewed
  operational assertions and makes no rights or narrative approval decision.
- The profile now keeps provider credit lists separate and expandable rather
  than choosing one provider's credits and hiding the rest. The sourced,
  commercial/open-rights list is shown first; local non-commercial-only
  credits remain clearly labeled and separate. Actor names and character
  labels continue to link to their respective evidence. This avoids blending
  conflicting provider data or implying that restricted data is cleared for
  commercial use.
- The local profile now exposes both Wikidata (20 sourced credits, 17 cast)
  and IMDb Non-Commercial Datasets (15 sourced credits, 10 cast) for this
  canary, with character labels where retained. This is not a completeness
  claim for the film catalog; the wider rights and 100-film metadata review
  remains open. The local narrative rights queue still has 3,039 unreviewed
  snapshots and zero approved assets, so none is cleared for semantic
  indexing.
- Verification: frontend unit suite **5 passed**, TypeScript check passed,
  and full Playwright suite **10 passed**. Working-corpus writes were limited
  to the described Wikidata CC0 label snapshots/assertions; no narrative
  snapshot decisions, embeddings, or vectors were written.

### Follow-up — refreshed pilot baseline and namespace-safe metadata audit

- Revalidated the frozen selection against its exact CSV/readiness/IMDb-review
  hashes: **100 unique candidate records**, 77 exact title/year matches and
  23 identity crosslinks explicitly scoped to pilot membership. The latter
  are not catalog merges or permission to reuse IMDb fields.
- Generated fresh local-only reports from read-only transactions against the
  working catalog: `catalog-readiness-v7.json` (2,586 films) and
  `catalog-pilot-metadata-audit-v11.json` (the frozen 100). The readiness
  projection finds section headings for plot in **99/100**, production in
  **96/100**, reception in **100/100**, and themes/analysis in **46/100**.
  These are section-presence signals, not proof that a passage is sufficiently
  detailed or useful. All 100 have resolved director and cast assertions;
  43 have at least one resolved character assertion, which does not establish
  a complete or default-display-eligible actor/character mapping. One film,
  *Hamilton*, has no plot-labelled passage.
- The 100-film set has **208** narrative source snapshots with license and
  attribution recorded, but **zero** explicit use decisions and **zero**
  snapshots eligible for semantic indexing. It has **7,270** stored vectors,
  but **zero** vectors currently eligible under the rights gate. These counts
  explain why existing vector volume is not usable retrieval coverage. No
  review decisions or vectors were added by this audit.
- The fresh date/runtime projection repeats the unresolved field-level gaps:
  81 legacy profile dates are empty; 3 match the earliest recorded event, 2
  match an earliest-year event whose ordering is unknown, 13 match another
  territory event, and 1 same-year date has no exact event match. Runtime
  evidence provides 117 displayable options for 99 films (16 version-scoped);
  17 films still require value/version resolution and one has only restricted
  runtime evidence. The report exposes evidence and qualifiers without
  selecting a preferred edition.
- Corrected `audit_pilot_metadata_projection.py` to accept explicit,
  component-bounded snapshot path mappings and to count distinct snapshot IDs
  rather than duplicate assertion-evidence references. The v11 audit mapped
  only the mounted, read-only Docker raw-snapshot volume: **194 unique
  snapshots verified**, **14 unmapped**, **0 missing**, **0** evidence rows
  without a source snapshot. “Unmapped” means the historical path was outside
  this container's authorized mounts; it does not assert that host bytes are
  absent. The earlier no-map interim report was discarded; its Docker-local
  `missing` counts were not valid host-integrity findings.
- Verification: focused projection/path-map tests **3 passed**, including the
  PostgreSQL case against `cinegraph_test`; full non-integration backend suite
  **297 passed, 88 deselected**; full isolated API/PostgreSQL integration
  suite **87 passed, 1 skipped** against `cinegraph_test`; the manifest
  validator still confirms all three input hashes and 100 unique candidate
  IDs. Reports and source data remain local/ignored.
  The next gate is source- and purpose-specific review of the 208 narrative
  assets plus a sampled content/identity review; this audit does not authorize
  semantic indexing or certify the 100-film set as complete.

### Follow-up — render the frozen pilot as a film-by-film coverage sheet

- Added `scripts/render_catalog_pilot_coverage.py`, a local-only deterministic
  renderer joining the frozen 100-film manifest to the read-only readiness and
  metadata audits. It verifies the manifest hash carried by the metadata audit,
  checks all 100 candidate IDs and Wikidata IDs across reports, and validates
  the selection-only identity-decision sidecar against the exact pilot bytes.
  The 23 approved pilot-membership crosslinks are labeled as such, not as
  catalog merges; the report shows both selected-list and canonical catalog
  titles when they differ. It rejects any sidecar that grants operational
  merges or product-field authorization.
- Generated the ignored/local `data/evaluation/catalog-pilot-coverage-v4.md`
  (SHA-256 `972ec94ae2289aae03f17c9814f6239046a53e976497ca5177c3e80fb2fc877e`).
  It makes the pilot's actual state readable in one place: 77 exact
  title/year rows and 23 membership-only crosslinks; plot/production/reception
  section presence of 99/100, 96/100 and 100/100; 208 attributed narrative
  snapshots but zero approved and zero eligible; 7,270 stored vectors but
  zero rights-eligible vectors; and 194 verified / 14 unmapped snapshot paths
  in the limited release/runtime evidence audit. Per-film rows expose section
  presence, resolved director/cast/character assertion counts, legacy versus
  research release fields, runtime options and eligible-versus-stored
  narrative/vector counts. A section heading is not a quality judgment, and
  resolved assertion presence is not proof of correctness or complete credits.
- The pilot is not English-only: the catalog currently labels 72 films `en`,
  5 `hi`, 2 `ta`, 1 `ml`, 1 `mul` and 19 `und` (unclassified). Therefore this
  report cannot be described as a fully English-language pilot; in particular,
  unclassified titles should not be silently treated as English. Language codes
  are shown in the summary and per-film table.
- Added four fixture-based tests covering report joins, pilot-hash mismatch,
  pilot-only crosslink labeling/title display, and rejection of broader
  authority or wrong-film decisions. The focused suite passes **4/4**; the
  complete non-integration backend suite passes **301 tests, 88 deselected**.
  The renderer writes only under ignored `data/evaluation/`; it does not access
  the database, crawl sources, or change corpus facts, snapshots, decisions or
  vectors.
- This completes the Phase A *coverage-sheet* artifact, not the entire Phase A
  baseline: a fresh question-conditioned retrieval output/latency baseline and
  human content review remain separate. The narrative-rights and
  source-eligibility gates also remain closed for the current 100-film corpus.

### Follow-up — correct operator-access documentation

- Audited the active intake route against the expansion plan. The current gate
  compares a configured email string in `x-operator-email`; it is not a bearer
  credential or proof of identity, and the API explicitly disables it outside
  `development` / `local`. Docker binds the API to `127.0.0.1` by default. The
  intake UI already describes this as a local pilot and says sign-in is needed
  before public deployment.
- Corrected the expansion plan's stale claim that the local intake has an
  authenticated bearer token. This avoids treating email-only local access as
  an admin-authentication feature or shipping it as a production boundary.
  Production authentication remains unimplemented and is a go-live blocker.
- This documentation audit made no access-control, data or runtime changes.
- Read-only runtime check: Compose API and PostgreSQL were healthy, but no
  `intake_worker` container was running because this local stack had been
  started with a service subset. The rights API still reported **3,039**
  unreviewed snapshots; the two *The Dark Knight Rises* snapshots were both
  unreviewed English Wikipedia / CC BY-SA 4.0 records. No decision was written.
- Checked the intake queue before starting the worker: it contained four jobs,
  all legacy terminal states (`ready` / `ready_with_gaps`), with no queued or
  running jobs. Started `intake_worker`; it remains running and idle, with no
  source job claimed and no queue-state change. The local frontend returned
  HTTP 200. No source request or catalog write occurred.
- Corrected the local intake runbook and README: `docker compose up --build -d`
  starts the worker and may resume already queued work; starting only `api web`
  leaves new jobs queued unless `intake_worker` is also started. Replaced stale
  service-token and `ready` status instructions with the current local email
  gate and `captured` / `captured_with_gaps` meanings.

### Follow-up — original-language evidence is inspectable in film profiles

- The research API already returned source-backed original-language Wikidata
  item IDs and field-level provenance, but the film profile displayed only a
  short catalog code. For unsupported source languages this appeared as
  `UND`, hiding the actual recorded evidence; multiple source languages were
  similarly collapsed to `MUL`.
- Updated the profile to call this value a **catalog language code** when
  research metadata is present, and added a collapsible evidence section with
  every recorded language item ID and its source URL, license and revision.
  `und` is explicitly described as unmapped by the current language-code
  configuration, not as missing source data. Multiple source entries are
  inspectable rather than flattened into an apparent single-language fact.
- Added an open CC0 language assertion to the isolated Dark Knight fixture and
  browser assertions for the code, item link and source revision. Frontend
  unit tests pass **5/5** and the production build/type check passes. The
  Playwright/API integration did not pass in this environment. The test stack
  was later reachable, but its film-search route returned HTTP 500; details of
  the isolated stack failure are recorded below. No working-corpus data was
  changed.
- This improves evidence visibility but does not resolve the underlying
  language model: `original_language_code` remains a limited catalog
  classification, and source disagreements still need review. The browser
  assertion is pending successful execution against the separate
  `cinegraph_test` stack. The attempted suite reached 56 passing tests before
  the host could no longer connect to the test database on port 5433; the
  resulting 17 failures and 14 setup errors were database-connection failures,
  not assertions about language behavior. The focused Playwright run then
  found the isolated API health route responsive but film search returned
  HTTP 500. Docker reported an I/O error reading the PostgreSQL image layer
  and container logs, so the test DB container was not forcibly replaced and
  no Docker images or volumes were pruned. Working API/database ports were
  not listening in this session. Treat browser/API verification as unresolved,
  not passed.

### Follow-up — separate the English-first pilot from the multilingual list

- The earlier frozen global top-100 manifest was not an English-only sample:
  its catalog language distribution was 72 `en`, 5 `hi`, 2 `ta`, 1 `ml`, 1
  `mul`, and 19 `und`. Reusing it as the English-first pilot would silently
  mix language editions and unknown classifications.
- Added a deterministic, offline selector and validator in
  `backend/app/services/english_catalog_pilot.py` and
  `scripts/freeze_english_catalog_pilot.py`. It uses the local IMDb CSV only
  for ordered title/year candidates, matches only exact title/year or catalog
  aliases against the read-only catalog readiness report, selects only
  distinct catalog films recorded as `en`, fingerprints both input artifacts,
  and records skipped rows. It does not change catalog identities or grant
  source/data rights.
- The local-only `data/evaluation/catalog-pilot-english100-v1.json` validates
  against its exact inputs: 100 unique films, all 100 exact title/year
  matches, scanning through input rank 165. Before reaching 100, 37 rows had
  no exact title/year match and 28 matched only a non-English or unclassified
  catalog record. The Godfather (rank 2), The Dark Knight (3), Interstellar
  (22), and Avengers: Endgame (60) are present. CSV SHA-256:
  `6b8695e6efee6941bbeb0fb391538d1f7798290412b911f4f3db897f155af744`;
  readiness-report SHA-256:
  `271fc6354b7fea91ff8fdb11ae2502e12b20fe075b1a5baca5df6d3476a357e4`.
- Added four pure tests for deterministic selection, exclusion/ambiguity,
  fingerprint validation and insufficient candidate counts. The selector and
  manifest-gate tests pass **15/15**. The candidate manifest remains ignored
  local evaluation data and was not added to Git. This is a target-list gate,
  not the requested film-by-film source/rights/content review.
- Corrected Phase D: the existing 50 questions are already inspected and are
  development/regression data, not a holdout. Their 80% threshold is now
  explicitly a development gate only. A separately frozen, film-pair-disjoint
  holdout must be labeled and evaluated untouched before any release-quality
  claim; existing draft questions and single-reviewer judgments do not yet
  satisfy that gate.

### Follow-up — freeze the supplied Top-1,000 candidate denominator

- Added `backend/app/services/english_catalog_target.py` and
  `scripts/freeze_english_catalog_target.py` to freeze the first 1,000 data
  rows of the supplied CSV as an explicit, deterministic source-list target.
  This is not an English-only list: its language composition is unresolved
  until source-backed identity/language review. The CSV
  has 1,001 data rows: rank 1,001 is `The Hobbit: The Battle of the Five
  Armies` (2014), recorded explicitly as out-of-scope rather than silently
  discarded. The artifact
  contains only source rank, input row, title, release-year candidate and an
  unresolved identity status, plus the exact CSV SHA-256. It intentionally
  excludes overview, ratings, gross, cast, crew and other CSV fields.
- Duplicate title/year rows are retained in rank order and marked for identity
  review rather than silently deduplicated. The repeated `Drishyam` entries
  have different years and remain separate candidates; title alone is not an
  identity key.
- The generated manifest is local-only under ignored
  `data/evaluation/catalog-target-english1000-candidates-v1.json`. It is a
  candidate denominator, not a current/official IMDb ranking, verified English
  catalog, ingestion authorization, or evidence-quality claim. Catalog identity
  resolution, language adjudication and per-film source/rights review remain
  separate gates.
- The command refuses a different CSV path, fewer than 1,000 rows, malformed
  selected title/year rows, and overwriting an existing artifact. It records
  rows after the first 1,000 as out of scope. `--validate`
  deterministically rebuilds and compares the artifact against the exact
  source bytes. Small synthetic tests cover field minimization, duplicate
  handling, malformed input and fingerprint drift.

### Follow-up — read-only identity candidate audit for the full target

- Added `backend/app/services/english_catalog_target_resolution.py` and
  `scripts/audit_english_catalog_target.py`. The audit joins the frozen target
  against one local readiness snapshot using exact normalized canonical
  title/year first, then exact alias/year. It makes no fuzzy match, network
  call, catalog write or identity decision; inputs and report remain local.
- Against `catalog-readiness-v7.json`, the 1,000 candidates produce 781 unique
  exact canonical title/year candidates, 1 ambiguous title/year candidate and
  218 unmatched candidates. Of the 781 unique candidates, 684 point to records
  labeled English and 97 point to another or unknown/multiple language state.
  These are counts of candidate joins, not verified identity or evidence
  quality. The ambiguous 2011 *The Girl with the Dragon Tattoo* row maps to
  both the Swedish and US film records and requires human/source-ID resolution.
- The local identity report is bound to exact target and readiness hashes and
  revalidates deterministically. It is not committed and does not modify the
  working database. Next, resolve unmatched/ambiguous titles with stable IDs
  from permitted sources, confirm original language, then run the existing
  source-capture and rights gates per resolved work.

### Follow-up — use the local IMDb index only as a restricted identity-review aid

- Added `backend/app/services/english_catalog_imdb_review.py` and
  `scripts/review_english_catalog_target_imdb.py`, reusing the existing local
  title index to search only the 219 unmatched/ambiguous target rows. The
  script is offline, year-bounded (±1 year), caps results at eight per title,
  and cross-checks IMDb title IDs against catalog `resolved_imdb_ids`. It does
  not fetch or write source data, alter the target manifest, merge catalog
  entities, or approve product use.
- The local report found 189 unique exact title/year IMDb-ID-to-catalog
  crosslink candidates, 3 unique exact IMDb title/year candidates without a
  catalog crosslink, and 27 rows without an exact IMDb title/year candidate.
  All 219 remain explicitly `review_required`; the 189 are strong leads, not
  reviewed identity decisions. The ID joins depend on existing catalog
  assertions and should be verified from retained source evidence before any
  operational merge.
- This remains a local, non-commercial research aid only. IMDb's terms do not
  authorize carrying this index or its fields into a paid product. Output is
  ignored under `data/evaluation/`, bound to target/readiness/audit/index
  hashes, and can be regenerated and validated deterministically.

### Follow-up — per-title data coverage for the supplied 1,000 candidates

- Added `backend/app/services/english_catalog_target_coverage.py` and
  `scripts/render_english_catalog_target_coverage.py`. The report joins the
  exact target, readiness, identity and restricted IMDb-review artifacts by
  rank and file hash. It shows catalog coverage and source-use eligibility
  without copying narrative text or changing the working DB. Local JSON and
  Markdown outputs remain ignored under `data/evaluation/`.
- The current candidate mapping yields 969 unique catalog candidate rows, 1
  ambiguous row, and 30 rows without a current catalog candidate. The 969
  candidates have language labels: 730 `en`, 50 explicitly non-English
  (`hi`, `kn`, `ml`, `ta`, `te`), 182 `und`, and 7 `mul`. Therefore
  this supplied global Top-1,000 list is not yet an English-only corpus.
- Among the 969 mapped candidates, 967 have a plot section, 912 production,
  966 reception, 258 themes/analysis, 349 legacy/influence and 527
  writing/craft. All 969 have at least one resolved release-event, runtime,
  director, writer and cast assertion; only 127 populate the older profile
  release-date and runtime fields. This points to a projection/UI distinction,
  not absence of all source data. 257 have at least one resolved character
  assertion, while the legacy credit table exposes no character labels.
- **0/969** mapped candidates have any snapshot currently eligible for
  semantic/model use, and **0/969** have any eligible embedding vector. The
  main retrieval gate is still rights approval, not running a larger embedding
  model. Section presence and resolved assertions do not establish factual
  correctness, complete credits, meaningful relevance or reuse permission.
- The report is a coverage diagnosis only. Before calling this the English
  1,000, resolve all language-unknown candidates and either choose a separately
  justified English-only denominator or explicitly keep the target global.
- Coverage report v3 now records per-title, non-exclusive pipeline gates and
  review reasons in addition to field counts: `requested`, unique
  `catalog_identity_candidate_resolved` (still unreviewed),
  `narrative_evidence_ready`, `semantically_indexed`, and `review_required`.
  On the current local inputs these counts are **1,000 / 969 / 0 / 0 / 1,000**.
  The report distinguishes candidate identity from verified identity and
  rights-cleared evidence from stored vectors; 0 evidence-ready and 0 indexed
  is not misreported as a retrieval failure. The generated v3 Markdown/JSON
  remain ignored local artifacts.

- The coverage join now rejects duplicate selection ranks, duplicate readiness
  film IDs and out-of-target IMDb-review ranks rather than silently letting a
  later row overwrite an earlier one. Focused target/identity/IMDb/coverage
  tests pass **14/14**, and the local report validator confirms all 1,000 ranks
  against the current input hashes. This is an offline report gate only.
- The full backend non-integration suite passes **353 tests, 88 integration
  tests deselected** when run with the project Conda interpreter and the
  documented local `data/vendor/mwparserfromhell` fallback on `PYTHONPATH`.
  The run emits a non-fatal PyTorch/NumPy initialization warning and a spaCy
  deprecation warning; model-inference evaluation still needs its own runtime
  check. An initial attempt without the documented fallback failed collection
  on six imports; no environment packages were installed or changed.
- The isolated integration gate remains open: a read-only `docker compose ps`
  check reports both `db` and `api` containers running but **unhealthy**. No
  integration tests, migration, replay apply, corpus query, or corpus write
  was attempted in this step.
- A read-only inspection of their health-check history returns `input/output
  error` while executing even `/bin/sh` in PostgreSQL and `/usr/local/bin/python`
  in the API container. This is below the application/test layer and matches
  the previously observed Docker Desktop/containerd storage failure. No
  restart, prune, image rebuild, or volume recreation was attempted; those
  actions could put the persistent local corpus at risk.

### Follow-up — English pilot coverage sheet

- Added `scripts/render_english_catalog_pilot_coverage.py`, which verifies the
  English pilot against the exact local candidate CSV and readiness report
  fingerprints before rendering. It cross-checks all 100 catalog IDs, QIDs and
  English language states, and reports film-by-film sections, release years,
  runtime presence, director/writer/cast/character assertion counts, snapshot
  rights states, stored-versus-eligible vectors and existing readiness gaps.
- Generated local-only
  `data/evaluation/catalog-pilot-english100-coverage-v2.md` (SHA-256
  `193bc74fab98ca64f2028db7f507f6293d818544c77c4cb3f93c754f928d9596`). The
  100 selected films have plot sections for 99, production and reception
  sections for 100, themes for 46, and writing-craft sections for 80. Their
  200 narrative snapshots have license/attribution metadata, but **0** are
  approved or eligible for semantic use; all **7,466** stored vectors are
  ineligible under the current rights policy. This is the most important
  operational limitation for the planned retrieval layer.
- The report explicitly omits source-text review and the separate
  release/runtime snapshot-integrity audit; its counts do not certify correct
  credits, character mappings, story quality or legal clearance. Those remain
  Phase A/B work. The report has no narrative text and remains ignored local
  evaluation output.
- Added six pure renderer tests. Full non-integration backend tests pass
  **311 passed, 88 deselected** when using the project Conda test runner with
  the project venv's `mwparserfromhell` package on the import path. The Conda
  environment alone lacks that parser dependency; no environment or files
  outside this repository were changed.

### Follow-up — exact-source capture for all English pilot titles

- Added offset-based, checkpoint-friendly capture batches to the existing
  sequential Wikimedia capture adapter. It accepts the frozen English pilot
  manifest and validates each selected row's English classification, exact
  title/year match, catalog film ID and Wikidata QID before capture. Existing
  robots checks, one-request-at-a-time operation, minimum one-second request
  spacing and stop-on-denial/rate-limit behavior remain in force.
- Captured pilot ranks 11–100 (90/90 identity-verified; 90/90 Wikipedia pages)
  into ignored local evaluation storage. Together with the previously captured
  exact ranks 1–10, the pilot selection has matching retained source bundles;
  these captures have not been inserted into PostgreSQL or the embedding
  index, and they do not imply narrative rights approval.
- Corrected audit semantics so absent plot/production sections are explicit
  content-coverage gaps rather than false capture-integrity failures. Hash,
  identity, revision-binding and deterministic-parser mismatches remain hard
  failures. The updated 90-title audit passes source-integrity checks **90/90**
  with **3,210** passages; plot is present for 89/90, production 90/90,
  reception 90/90, themes/analysis 36/90 and legacy 43/90. Hamilton is
  explicitly listed as the one plot gap.
- The 90-title bundle contains 2,213 Wikidata cast statements; 1,056 (47.7%)
  carry a character entity/name qualifier and 1,157 do not. Wikidata contains
  release-date values for 90/90 films (396 statements, 346 territory-qualified,
  340 source-referenced) and runtime values for 90/90 (105 statements). These
  are retained-source counts, not reviewed truth or proof that the application
  projection displays them.
- The ten-title bundle independently reports 484 passages, 426 citation
  marker-bearing passages (88.0%), and 328 cast statements, 214 with a
  character qualifier. It includes The Dark Knight with 29 cast statements,
  17 role-qualified. Citation marker presence is not itself citation support
  or permission to redistribute.
- The updated full non-integration backend suite passes **322 tests, 88
  integration tests deselected**. Frontend unit tests pass **5/5** and the
  production build/type check succeeds. Docker reports the working API and DB
  as unhealthy; reading PostgreSQL container logs still fails with an
  image-layer `input/output error`. Thus database/API integration and browser
  E2E remain unverified. The existing narrative rights gate remains closed
  (0/200 approved for the 100-film narrative corpus), so these new pages are
  local research/QA material only, not searchable production evidence.

### Follow-up — reconcile the exact English 100 source captures

- Added an offline reconciler that reruns the hash, identity, revision-binding
  and deterministic-parser audit for each bundle, then compares every
  `selection_rank` / title / year / QID against the frozen English pilot. This
  exposed and preserves the provenance distinction: ranks 11–100 were captured
  directly from the frozen English manifest; ranks 1–10 came from a previous
  manifest with a different SHA-256, but each exact row matches the English
  pilot. The report does not claim the two source manifests were identical.
- Local output `data/evaluation/english100-capture-reconciliation-v4.md` and
  JSON reconcile **100/100 unique ranks**, **3,694 passages**, and **3,165
  citation-marker-bearing passages (85.7%)**. Plot sections exist for 99/100,
  production and reception for 100/100, themes/analysis for 43/100 and legacy
  for 50/100. Hamilton is the one missing plot section. These are section
  availability counts, not semantic completeness judgments.
- Across the captured Wikidata payloads there are 2,541 cast statements;
  1,270 carry a P453/P4633 character qualifier and 1,271 do not. Release dates
  have 447 statements across 100 films (395 territory-qualified, 378 with a
  Wikidata reference); runtime appears on all 100 (118 statements). These
  payload counts do not prove that the local DB/API projects or displays every
  statement; no structured statements were ingested into the working DB in
  this step.
- The capture audit schema is versioned as v2 to distinguish content gaps from
  capture integrity. The reconciler has pure tests for exact identity matching,
  distinct selection hashes, duplicate-ID rejection, missing-content reporting
  and integrity failure. It retains the capture-policy and robots.txt hashes
  for each batch. Full offline backend tests pass **323 passed, 88 deselected**;
  frontend unit tests **5/5** and production build pass. The local JSON includes
  hashes and detailed per-film counts and remains ignored; no source prose/raw
  payload was added to Git.
- Re-ran the retained-input command on 6 November with the project Conda
  interpreter and the repository's ignored vendored parser fallback. The
  offline v2 replay again validates the exact 100 film/page identities, source
  hashes and current v6 deterministic passage derivatives: **100 films**,
  **21,744,082 Wikidata bytes**, **77,560,804 Wikipedia HTML bytes**, and
  combined manifest digest
  `835bf314ff069248e3a24af9a30133fd916b13a39a10a77e30dede6d1bb2408f`.
  The replay says `ready_for_database_preflight`, which means only that local
  inputs passed; it does not mean the DB identity preflight passed or that
  anything was ingested. No apply, DB query, or corpus write occurred.

### Follow-up — local corpus storage unavailable; ingestion remains stopped

- Rechecked Compose status before attempting any data write. The `db` and `api`
  containers are running but unhealthy. Docker health checks fail with
  `input/output error`; a read-only PostgreSQL connection fails because the
  server cannot open `global/pg_filenode.map`. Reading the database container
  log and Docker's image-usage summary also fails on containerd blob/log
  `input/output error`. This points to Docker Desktop storage trouble, not a
  source-capture or application-level validation failure.
- Host disk inspection showed only **4.3 GB free**. Project-local ignored data
  occupies about **17 GB**, mostly model weights, local environments and
  evaluation artifacts. The large directories are referenced by current
  experiment documentation/scripts; none were deleted. No Docker restart,
  prune, volume recreation, migration, or corpus write was attempted, to avoid
  risking the persistent working database.
- The host Conda settings currently fall back to SQLite when no
  `DATABASE_URL` is loaded. A read-only probe initially hit that fallback and
  was stopped; it did not query or write the catalog. Future local pipeline
  commands must explicitly load/check their database target before running.
- The ignored root `cinegraph.db` is an existing **24 MB** SQLite catalog
  (file timestamp 12 August 2026), not an empty file created by that probe. It
  was inspected read-only and left untouched; it is not the Compose
  PostgreSQL database and must not be treated as interchangeable with it.
- The 100-film source captures and reconciliation remain complete as local QA
  artifacts, but have **not** been ingested or indexed. Narrative semantic-use
  approval is still 0/200 snapshots. Therefore the 100-film enrichment and
  retrieval-quality gates remain open; the capture count must not be reported
  as dataset readiness.
- The pending original-language evidence UI change passes frontend unit tests
  (**5/5**) and a production build/type check. Its browser contract remains
  unverified because the isolated PostgreSQL/API stack cannot run against the
  current Docker storage state. The language fixture change and UI work remain
  local and uncommitted pending that gate.
- Safe next action: recover Docker Desktop storage / restore an existing local
  database backup, then verify the schema and run the isolated `cinegraph_test`
  suite before retrying any corpus integration. Do not remove or recreate the
  PostgreSQL volume without a verified backup.

### Follow-up — local database target no longer silently defaults to SQLite

- Changed the host-development default to the Compose PostgreSQL catalog on
  `127.0.0.1:5432`. A missing `DATABASE_URL` now surfaces an unavailable local
  PostgreSQL service instead of silently targeting the separate SQLite
  `cinegraph.db` catalog; Compose and tests can still provide explicit URLs.
- Added a pure settings test for the default target. Focused config tests pass
  **7/7**; the full backend non-integration suite passes **324 tests, 88
  integration tests deselected**. This does not validate PostgreSQL health or
  migrations. Database/API integration remains blocked by the recorded Docker
  storage I/O failure; no corpus database was queried or changed by these
  tests.
- Frontend tests remain **5/5** with a successful production build/type check.
  The separate original-language browser assertion still needs a healthy
  isolated `cinegraph_test` stack before it can be considered verified.

### Follow-up — retained English pilot Wikidata replay is prepared, not applied

- Added `english_pilot_raw_replay`, an offline-by-default replay command for
  the two retained capture batches. Its dry run re-audits the frozen English
  pilot rows, both capture manifests, robots policy fingerprints, source
  revisions, exact SHA-256 bytes and article-page identity for all 100 films.
  The current run validates **21,744,082 Wikidata JSON bytes** and **77,560,804
  Wikipedia HTML bytes** across the same 100 exact film identities. It binds
  the selection, both capture-manifest hashes and both `robots.txt` hashes
  into a deterministic input digest. The local command is:
  `PYTHONPATH=backend python -m app.services.english_pilot_raw_replay`.
- Once the local Compose catalog is healthy, build the current API image and
  use a one-off API container for apply:
  `docker compose build api && docker compose run --rm --no-deps api python -m app.services.english_pilot_raw_replay --apply`.
  The one-off container receives the ignored local `data/` tree read-only for
  input and the shared raw-snapshot volume for output; it uses the current
  source code without restarting or recreating the database service. The
  command still performs its exact database identity/schema preflight before
  writing.
- An explicit `--apply` path is fenced to the local Compose `cinegraph`
  PostgreSQL service and the shared `/var/lib/cinegraph/raw-snapshots` volume.
  It requires a current schema and verifies that each Wikidata QID still maps
  to the exact frozen catalog film UUID before writing. It saves an
  input-hashed replay manifest to the shared volume, retains structured
  Wikidata snapshots/assertions and exact CC BY-SA 4.0 Wikipedia HTML source
  snapshots/page assertions, then projects supported facts through the
  existing `Assertion` pipeline. It does **not** persist narrative passages,
  create narrative-use approvals, or build embeddings; source text remains
  ineligible for semantic/model use until the separate snapshot-scoped review
  gate. The working DB is currently unhealthy, so this write path was **not**
  applied.
- Made raw assertion replay idempotently backfill newly supported statement
  fields from the exact retained EntityData bytes; the existing source
  assertion locator/version key prevents duplicates. The isolated PostgreSQL
  integration test now simulates a missing prior statement and checks its
  recovery, manifest hash and robots hash. That integration test is not yet
  executed because of the Docker storage I/O failure.
- Added pure route-policy/path-containment/hash tests. Full backend
  non-integration suite passes **339 tests, 88 integration tests deselected**.
  The full local 100-capture dry run succeeds; integration, API, browser and
  database write gates remain pending recovery of local PostgreSQL storage.
- No capture payload, snapshot, vector, rights decision or corpus row was
  modified in this step. The replay output is a validated preflight, not a
  claim that the data is searchable or ready for a writer-facing quality gate.
- Tightened the offline replay validator to require the frozen pilot's exact
  100 contiguous ranks and to reject symlinked capture manifests or payloads.
  The focused replay tests pass **9/9**, and the full non-integration suite
  passes **333/333** with integration tests intentionally deselected. Frontend
  tests pass **5/5**, and the production build/type check succeeds.
- Integration was retried without touching the corpus database. The existing
  `cinegraph_test` container is healthy but has no host port mapping; the
  project runner cannot recreate its migration image because Docker reports a
  containerd blob `input/output error`. A direct isolated-schema test therefore
  failed to connect (`127.0.0.1:5433` refused) before executing assertions.
  This leaves the replay persistence behavior unverified, not failed. No
  database writes occurred.
- Tightened capture-policy numeric validation so boolean, NaN and infinite
  request intervals cannot be accepted as a valid rate-limit record. The
  validator also rejects malformed pilot/capture JSON shapes with explicit
  replay errors before any database preflight. The focused replay suite then
  passed **15/15** and the full non-integration suite passed **339 tests**. At
  that checkpoint, a fresh 100-capture dry run still validated all
  **21,744,082** Wikidata payload bytes with the same combined input digest.
- Extended the replay to include the 100 retained Wikipedia article HTML
  snapshots. Before any DB access, the dry run checks the exact page bytes,
  SHA-256, article URL policy, CC BY-SA 4.0 declaration, QID, page ID, resolved
  title and revision against both capture manifests; both batches must share
  the same recorded Wikipedia robots fingerprint. The verified capture set is
  **77,560,804 HTML bytes** plus the Wikidata payloads above; the v2 combined
  input digest is `835bf314ff069248e3a24af9a30133fd916b13a39a10a77e30dede6d1bb2408f`.
  On `--apply`, the existing `ingest_captured_article` path stores immutable
  HTML snapshots and source-page assertions and records the replay manifest
  hash for each run.
  It does not create narrative passage rows, rights approvals or embeddings;
  the existing snapshot-scoped semantic-use gate remains closed by default.
- The Wikipedia persistence integration assertion now checks its manifest
  hash, but remains unexecuted because the isolated PostgreSQL service cannot
  be reached from the host and Docker cannot recreate its test image. The
  offline replay stays green; no database or source artifact was modified.

### Follow-up — derive review-only cast and character candidates

- Added an offline adapter for explicit `Actor as Character` phrases in
  cast-labelled sections of retained English Wikipedia passage derivatives.
  Exact actor labels already captured from Wikidata may be linked to their
  QID. Other names remain `unresolved_source_name` with no actor QID. Group
  roles and empty role labels are quarantined. Every row remains
  `review_required`; the report has `operational_fact_write: false` and does
  not write to the database, fetch the web, approve semantic use or create
  embeddings.
- Ran the adapter across the retained rank 11–100 capture (90 films). All 90
  have a cast-labelled passage and at least one explicit candidate phrase.
  The report contains **1,831 candidates**: **1,365** have a captured Wikidata
  actor QID and **466** are source-only unresolved names. **232** candidate
  role labels also match a captured Wikidata character label after
  case/whitespace normalization; this is a string match, not proof of the
  actor-character assignment. **36** rows were quarantined (28 group-role and
  8 empty-role cases). Example rows include Matthew Broderick → Simba from
  *The Lion King* as an unresolved actor name, and source-linked
  Shameik Moore → Miles Morales / Spider-Man from *Spider-Man: Into the
  Spider-Verse*. These examples are candidates, not approved credits.
- The initial v4 local report was
  `data/evaluation/catalog-intake/english100-rank11-100-v1/wikipedia-cast-candidates-v4.json`;
  it is ignored by Git with the capture data and has since been superseded by
  the identity-resolution follow-up below. The script verifies the capture
  and label manifests, Wikipedia CC BY-SA 4.0 attribution URL, snapshot and
  derivative hashes, parser/source revision binding and source locator before
  emitting candidates. A representative manual inspection of *The Lion King*,
  *Spider-Man: Into the Spider-Verse*, *Avengers: Endgame* and *WALL·E* found
  explicit names and roles retained with their cast-section provenance; absent
  Wikidata actor IDs remain unresolved rather than guessed.
- Added focused parser and integrity tests, including duplicate labels,
  multiline separation, middle initials, quoted nicknames, group roles and
  tampered content. Focused tests passed **13/13** before the final nickname
  refinement; the final focused cast suite passed **11/11**. The full backend
  non-integration suite passed **364 tests**, with **88 integration tests
  deselected**. This checks the offline adapter only; DB/API/browser publication
  and reviewed credit correctness remain open gates.
- No catalog rows, snapshots, vectors or rights decisions were changed. Next:
  resolve source-only people against permitted retained identity sources,
  review actor-character candidates (especially alternate/voice roles), then
  pass only approved mappings through the existing snapshot → source assertion
  → reviewed `Assertion` path. Do not treat the 90-film report as complete
  credit coverage or as evidence that the 1,000-film collection is vetted.

### Follow-up — resolve captured person identity without inventing film credits

- Added a deterministic offline identity pass over English labels and aliases
  in the already retained Wikidata snapshots for people referenced as cast,
  directors or writers in this same 90-film selection. It prefers a unique
  exact English label, then a unique exact English alias; ambiguous or missing
  matches remain unassigned. It does not use fuzzy matching, new requests or
  character labels as person identities. Every match includes the exact
  Wikidata EntityData URL, revision and snapshot hash.
- Reprocessed the unchanged 90-film source capture. Of 466 source-only names in
  v4, **38** now have a unique captured person identity (**25 label** matches,
  **13 alias** matches); **420 remain unresolved**. For all 38, the selected
  film-credit field `actor_qid` remains null: identifying a person from another
  captured film is not proof that they played the source-named role in this
  film. Existing same-film Wikidata cast references remain separately linked.
- The current ignored local report is
  `data/evaluation/catalog-intake/english100-rank11-100-v1/wikipedia-cast-candidates-v7.json`.
  Its SHA-256 is
  `ce6181526baaf575bf7fa829fd0b8861508720c5367342b098bd495c3275c686`.
  It contains 1,823 review-only candidates (1,365 with same-film Wikidata cast
  QIDs, 38 source-name identity suggestions, 420 unresolved names), 232
  string-only Wikidata character-label matches, and 44 quarantined rows: 28
  group roles, 8 empty role labels, one ordinal/company-name context, and 7
  overlong actor-name spans. Quarantine is retained for human review; it is not
  silently dropped. All candidate rows retain Wikipedia source URL, revision,
  passage hash and CC BY-SA attribution. None is an approved credit.
- Reviewed representative candidate and identity rows from *The Lion King*,
  *Spider-Man: Into the Spider-Verse*, *Avengers: Endgame*, *WALL·E*, *Goodfellas*,
  *The Dark Knight Rises*, and *Toy Story*. Exact-label and alias matches looked
  plausible in these examples, but the pass remains a candidate generator,
  not a complete manual credit audit. Some valid-looking multi-token actor
  names are deliberately quarantined by the conservative span rule for review.
- Focused extraction, capture-audit and identity-resolution tests passed
  **21/21**. The source-only identity resolver is pure and uses retained labels;
  no network, database, mock framework or operational fact write is involved.
  The full backend non-integration suite passed **371 tests**, with **88
  integration tests deselected**. The remaining integration/API/browser gates
  for catalog publication are not satisfied by this offline report.

### Follow-up — rank 11–100 Wikidata credit-label capture audited

- Completed the resumable EntityData capture for all **2,467** person and
  character QIDs selected from the retained rank 11–100 film snapshots. The
  capture is sequential and robots-checked; all rows record the same robots
  fingerprint, exact source URL/revision, retrieval time and snapshot hash.
  The local immutable snapshot bundle is **148,693,789 bytes** and remains
  ignored by Git.
- The offline audit verified all 2,467 snapshot hashes, manifest membership,
  QIDs, source revisions and URLs. It found **2,443 English labels** and **24
  QIDs without an English label**; those are explicitly unresolved. The target
  manifest has **2,213 cast**, **487 character**, **99 director** and **199
  writer** references. Across the 90 films, at least one English-named cast
  candidate is available for **82**, and at least one English-named character
  candidate for **55**. These are label coverage counts, not independently
  reviewed credit correctness or completeness.
- The audit report is retained locally at
  `data/evaluation/catalog-intake/english100-rank11-100-v1/credit-labels-v1/audit-v1.json`;
  no raw payload or audit bundle is committed. The focused capture/manifest
  suite passed **10 tests**, and the complete backend non-integration suite
  passed **353 tests** (88 integration tests deselected).
- Replay into `cinegraph_test` remains unverified. At inspection the dedicated
  test database container was exited/unhealthy and had no published host port;
  the working catalog database and API still reported container health-check
  `input/output error`. The existing integration API health endpoint answered
  `ok`, but that does not establish a reachable test database. No containers
  were restarted or recreated, and neither the test nor working database was
  written. Safe next action remains recovery of the isolated test database,
  followed by replay and API/UI verification against that database only.

### Follow-up — review-only cast source-statement bundle

- Added `wikipedia_cast_source_statements.py` and an offline CLI that converts
  the retained v7 candidate report into source-shaped `SourceAssertion` draft
  records. It accepts only exact same-film Wikidata cast identity matches;
  the 38 cross-film identity suggestions and 420 unresolved names are not
  promoted to source statements. Character QID string matches remain an
  explicitly labelled qualifier, not an accepted character identity.
- The bundle records the article URL, revision, snapshot SHA-256, CC BY-SA 4.0
  license/attribution, section locator, passage ordinal/hash, source phrase,
  and Wikidata cast statement locator. It is content-addressed and bound to the
  exact v7 report hash. All rows are `review_required`; the tool makes no
  database, rights-decision, operational assertion, or embedding writes.
- For the 1,823 existing candidates, **1,365** same-film identity records
  passed the draft gate and **458** identity-only/unresolved records were
  excluded. The local-only output is
  `data/evaluation/catalog-intake/english100-rank11-100-v1/wikipedia-cast-source-statements-v1.json`
  (SHA-256 `560403b94862e628823dbdae74d0f229fe639a9dc0b751834b3d478b0bd1c424`);
  it is ignored by Git. A sample for *Heat* retains Robert De Niro → Neil
  McCauley with its article and passage provenance, but remains a review
  candidate rather than a verified credit.
- Added 11 pure tests covering provenance, non-promotion, identity-only
  exclusion, malformed fields, duplicate statements and schema rejection.
  The focused test file passes **11/11**. The tool writes only inside the
  ignored local evaluation directory. It does not yet persist
  `SourceAssertion` rows: that requires the isolated PostgreSQL/API test gate,
  which remains unavailable due the known Docker storage/database issue.
- Next: restore `cinegraph_test` safely, add a real DB replay that joins each
  draft to exactly one retained `SourceSnapshot` by source URL, revision and
  content hash, then add an explicit reviewer decision path before projecting
  any cast-character `Assertion`. Do not infer that the candidate bundle is
  catalog completeness or publishable credit coverage.

### Follow-up — exact-snapshot cast statement replay (DB gate pending)

- Added a transaction-scoped replay service for the draft bundle. It requires
  exactly one successful English-Wikipedia `SourceSnapshot` matching article
  URL, revision, retained content hash, CC BY-SA 4.0 and attribution URL; it
  also verifies the local snapshot bytes and requires existing canonical film
  and person entities with the exact QIDs. It creates no identities, commits,
  rights decisions or operational `Assertion` rows.
- Replay is idempotent for byte-identical source statements and refuses to
  overwrite a conflicting existing statement. It validates each draft's
  content-addressed locator before database access, then preflights the full
  batch before adding any statement rows. The manifest remains review-only.
- Strengthened the manifest digest to cover all source statement content and
  qualifiers, including character-label-match context, so editing a draft
  invalidates its locator. This is explicitly versioned as source-statement
  schema v2 / extractor v2; v1 local artifacts remain untouched. The regenerated
  rank 11–100 bundle is
  `data/evaluation/catalog-intake/english100-rank11-100-v1/wikipedia-cast-source-statements-v3.json`
  (SHA-256 `4e85fffbd7782631f8c1ead1897dbe95b190e51bf066037c10894a667cb69921`):
  1,365 drafts and 458 excluded identity-only or unresolved candidates.
  The first-ten bundle is
  `data/evaluation/catalog-intake/first10-v1/wikipedia-cast-source-statements-v2.json`
  (SHA-256 `0a457b33a48bd53263e42ad725cce391aee2b51f6809f0a448ed19c4b28ad0c8`):
  181 drafts from 221 candidates, with 40 excluded. Both are ignored local
  outputs and were regenerated without overwriting prior immutable artifacts.
- Added three PostgreSQL integration cases for exact binding/idempotence,
  ambiguous snapshot rejection and source-byte checksum rejection, plus a pure
  tamper-detection test. The latest complete backend non-integration run passes
  **389 tests**; **91** integration tests were deselected. The three new DB
  cases compile but remain unverified: the daemon lists the isolated database
  container as healthy, yet `docker exec` reports that same container is not
  running, while the expected host port 5433 has no listener. The working
  corpus is exposed on 5432 and was not queried. No database rows were written.
- Keep this replay change local until those real PostgreSQL tests pass. Next:
  recover the Docker storage execution path, run these tests in `cinegraph_test`,
  then implement and test explicit review decisions before any operational
  cast-character assertion can be published.

### Follow-up — cast-candidate coverage extended to the first ten films

- Extended the offline cast-candidate preparation command to optionally bind a
  separate v6 passage-extraction manifest. It requires the same frozen
  selection, exact film QID set, article URL, revision and snapshot hash, and
  the expected parser version before using any derivative. This is additive;
  the rank 11–100 path continues to use the extraction binding already retained
  in its capture manifest.
- This exposed and fixed a pre-existing schema-check typo: the first-ten
  derivatives correctly declare `cinegraph.wikipedia-passage-extraction/v6`,
  but the candidate adapter had expected `/6` and rejected them. The adapter
  now reports which binding component fails rather than a generic mismatch.
- Prepared review-only candidates for all first ten films from their retained
  article revisions and credit-label captures. The local report is
  `data/evaluation/catalog-intake/first10-v1/wikipedia-cast-candidates-v1.json`
  (SHA-256 `323ad11b28e6223e412815b3c6bb073abd3010a9aac35eaa04e65bda529a6554`):
  10/10 films have cast passages and candidates; 221 candidate rows include
  181 same-film Wikidata cast identities, two identity-only suggestions, 38
  unresolved names and eight quarantined spans. The *Dark Knight* has 16
  explicit actor/character candidates; for example, Heath Ledger → the Joker
  has a same-film actor QID and a character-label QID match. Both remain
  review-required; the latter is only a string match, not proof of the credit.
- Prepared the first-ten review-only source-statement draft bundle at
  `data/evaluation/catalog-intake/first10-v1/wikipedia-cast-source-statements-v2.json`
  (SHA-256 `0a457b33a48bd53263e42ad725cce391aee2b51f6809f0a448ed19c4b28ad0c8`).
  It contains 181 exact same-film actor-identity drafts and excludes all 40
  identity-only/unresolved candidates. Together with the existing rank 11–100
  artifact, this now covers cast candidates for 100/100 pilot films: 2,044
  candidates, 1,546 same-film identity drafts, 40 additional identity
  suggestions, 458 unresolved names and 52 quarantined spans. These are
  extraction/identity coverage counts—not manual verification, completeness,
  permission to publish, or proof of correct actor-character attribution.
- Added six tests for extraction-manifest source binding. The focused binding
  and source-statement suites pass **18/18**. The PostgreSQL replay gate from
  the preceding follow-up remains pending; no source assertions or operational
  facts were added to either database.

### Follow-up — v2 statement digest and full offline regression (7 November 2026)

- The v2 source-statement digest covers the complete raw subject, value and
  qualifiers, including character-label match metadata. Old v1 local outputs
  were preserved; fresh v2/v3 immutable outputs are recorded above.
- Focused extraction-binding, statement and candidate-policy tests pass
  **36/36**. The full non-integration suite passes **389/389**, with **91**
  integration tests deselected. `py_compile` succeeds for the replay service
  and its DB integration tests; `git diff --check` is clean.
- The integration database cannot currently be exercised from this host: the
  Docker daemon's listing and exec state disagree, no listener exists on the
  configured test port 5433, and 5432 is the working catalog port. No attempt
  was made to use or alter that working catalog. Keep exact-snapshot replay
  local until the isolated test service is restored and the real PostgreSQL
  integration suite passes.

### Follow-up — reproducible 100-film cast review queue (7 November 2026)

- Added an offline audit/renderer that combines the first-ten and rank 11–100
  candidate partitions with their exact-input statement bundles, then checks
  every rank, title, year and Wikidata QID against the frozen English pilot.
  Capture partitions have different fingerprints by design, so the audit
  records both and uses the frozen pilot manifest—not an assumed shared hash—
  as the cross-partition identity authority. It checks report counters against
  rows, source revision/hash bindings, content-addressed draft integrity and
  one-to-one same-film candidate/draft counts.
- Generated local-only JSON and passage-free Markdown review artifacts:
  `data/evaluation/catalog-intake/english100-pilot-v1/cast-candidate-coverage-v2.json`
  (SHA-256 `371bc6b740ad8197a9d7aa87a11006f276aa2f81cd752ca00490559bbdd29bce`)
  and `data/evaluation/catalog-intake/english100-pilot-v1/cast-candidate-review-v2.md`
  (SHA-256 `650b3e563efb41a2a571a1aa5deebb925ba9e695242571d6c101c5f23d31455c`).
  Every article link uses the retained revision's `oldid`, not the mutable
  current article. The sheet gives a review queue for each of the 100 films.
- Reconciled totals are 2,044 candidates: 1,546 exact same-film actor identity
  candidates and review-only source drafts, 40 identity-only suggestions, 458
  unresolved names, 324 character-label-only QID matches, and 52 quarantined
  spans. Quarantines are reported by reason. None of these counts establish
  correct actor-character attribution or publication rights.
- Added three pure tests for disjoint-partition coverage, exact-input binding
  and tamper detection. Focused tests pass **21/21**; the full backend
  non-integration suite passes **392/392** and deselects **91** integration
  tests. The real PostgreSQL replay gate remains pending the isolated Docker
  database storage/execution recovery described above.

### Follow-up — cross-source cast-character coverage audit (7 November 2026)

- Added a reproducible offline crosswalk from extracted Wikipedia cast-role
  phrases to explicit Wikidata `P453` character qualifiers on the exact `P161`
  actor statement. It checks source revision/checksum bindings, statement and
  qualifier locators, actor/character QIDs, retained English labels, and exact
  label agreement. It also validates every candidate's section/ordinal,
  passage checksum and extracted evidence phrase against the retained passage
  derivative, itself bound to the captured Wikipedia article revision. This
  closes the risk that a candidate JSON row could claim text absent from its
  source passage.
- The 100-film result is stored as local-only artifacts:
  `data/evaluation/catalog-intake/english100-pilot-v1/wikidata-cast-character-crosswalk-v1.json`
  (SHA-256 `d6ebad5b875351c4972eb875587734aeb521747e2a06731b919993c9360ae5ba`)
  and its readable 521-row report
  `data/evaluation/catalog-intake/english100-pilot-v1/wikidata-cast-character-crosswalk-v1.md`
  (SHA-256 `20f784f88dc4c71ac34227cde8ebe5941b61dfeb29557b8ee3ca73b734f591ad`).
  Added a self-contained, searchable offline review page at
  `data/evaluation/catalog-intake/english100-pilot-v1/wikidata-cast-character-review-v1.html`
  (SHA-256 `e3e7c005e7726347e81ed7fef5b6dd7f176af310f44c6bda8cab59c72e3334fa`).
  It filters by film, exact-label agreement and title/actor/character text,
  pins both source links to captured revisions, omits the article prose, and
  marks all rows review-required. The report builder now rejects a candidate
  URL that differs from the retained canonical Wikipedia URL.
  Of 1,546 same-film actor candidates, 509 have at least one retained direct
  `P161`/`P453` link, producing 521 actor-character links. In 324 cases, the
  extracted Wikipedia role text exactly agrees with the captured English
  Wikidata character label. The Dark Knight example is Heath Ledger → the Joker
  (`Q163872`, revisions 2564648138 and 1383150687); exact label agreement is
  recorded separately from the source claims.
- These figures are extraction and cross-source corroboration coverage, not
  manual review, completeness, rights clearance, or publishable credit facts.
  All 521 links remain `review_required`; the audit writes no operational
  assertions. Exact English label agreement is not treated as independent
  proof that sources have identical scope.
- Added tamper tests for source passage evidence and HTML escaping. The focused
  crosswalk tests pass **4/4**, the standalone HTML parser confirms all four
  filter controls and all 521 rows, and the complete backend test run passes
  **410 tests** with **77** integration/environment-dependent tests skipped.
  Playwright is installed but its Chromium binary is not, so no browser
  screenshot was claimed. A fresh attempt to
  run the PostgreSQL gate still cannot reach execution: Docker Desktop reports
  blob-store I/O errors for the integration migration image and the running
  API container's `docker exec` returns input/output error; the existing
  `db-test` container is healthy but lacks the configured host port 5433. Both
  compose operations failed before changing the stack, and no test database
  statements were issued. The independent PostgreSQL replay gate remains
  pending; do not substitute the working corpus database.

### Follow-up — cast-candidate review and assertion projection (7 November 2026)

- Added an append-only `wikipedia_cast_review_decisions` ledger with per-source-
  assertion versions, reviewer, rationale and optional link to the existing
  operational `Assertion`. A PostgreSQL trigger rejects decision updates and
  deletes. This is a review record, not a second fact graph.
- Added a local-only API and operator screen for filtering and reviewing
  retained cast candidates. An approval revalidates the exact CC BY-SA article
  snapshot bytes, revision, attribution, candidate digest, retained passage,
  and pre-existing film/person QIDs before creating one source-linked
  `Assertion`. It will not create identities. Repeated approval reuses that
  assertion; a later rejection or deferral retracts it without deleting the
  candidate or review history. Non-approval decisions never create a fact.
- Added isolated PostgreSQL cases for approval/retry/retraction, absent passage
  rejection, non-promotion on reject/defer, admin route authorization and the
  database append-only trigger. The backend non-integration suite passes
  **410 tests**; **82 integration/environment-dependent tests are skipped** by
  the ordinary test command. The frontend production build and TypeScript
  checks pass, and Alembic reports `20261107_21` as the single head.
- The database runtime gate remains unverified: Docker reports the dedicated
  `cinegraph-integration-db-test-1` healthy, but `docker exec` reports that
  container is not running; recreating only `db-test` fails on a containerd
  blob-store I/O error. No integration statements were issued and the working
  corpus database was not used. Consequently, the new review UI/API has not
  yet been exercised against persisted pilot candidates; the exact-snapshot
  replay gate must pass first. Do not publish or count any of the 1,546
  candidates as reviewed until that real database workflow is verified.

### Follow-up — make the English-1,000 language gate explicit (7 November 2026)

- Reinspection of the frozen supplied 1,000-title candidate report showed it
  is not an English-only target: among 969 unique catalog identity candidates,
  730 carry `en`, 45 `hi`, 1 `kn`, 1 `ml`, 2 `ta`, 1 `te`, 7 `mul`, and 182
  `und`; 30 rows have no unique catalog candidate and one is ambiguous. The
  730 English-language rows are still unreviewed identity candidates, not a
  vetted English collection. The 50 explicitly non-English and 189 unresolved
  language rows cannot be silently counted toward one.
- Extended the read-only coverage report with per-row `english_target_status`
  and a separate `english_language_candidate` pipeline gate. It distinguishes
  English candidates, unresolved/multilingual labels, known non-English
  candidates, and unresolved identities. Bumped the report schema and default
  artifact names to v3/v5 so older local reports remain immutable.
- Regenerated and hash-bound the ignored local v5 JSON/Markdown report from the
  exact existing target, identity, IMDb-review and readiness inputs. Its
  validator passes and reports 730 English-language identity candidates out
  of 1,000 requested rows. No catalog records, source assertions, snapshots,
  passages or embeddings were changed.
- The focused coverage suite passes 4/4. The actual 1,000-English target
  remains incomplete: the supplied global list yields at most these 730
  English-labeled identity candidates and the current target includes
  non-English/unknown works. Constructing a true English 1,000 requires an
  explicitly scoped additional candidate source/list and identity/language
  review; do not rename this global list or inflate its denominator.
- The PostgreSQL integration gate remains unavailable in this environment:
  Docker's read-only container listing says `healthy`, but inspection reports
  `running=false`, no PID and no published port for the dedicated test DB.
  No working-corpus database was accessed.
- Rechecked the gate on 7 November: a disposable, loopback-only pgvector test
  container on port 5434 failed before creation because Docker Desktop could
  not read a containerd image blob. The pre-existing integration API container
  also returns a container-log I/O error. Its named test volume was preserved;
  port 5432 remains the separate working service and was not queried.
- Offline verification after the language-gate change: full backend suite
  **411 passed, 82 skipped**; frontend unit suite **5/5 passed** and production
  build/typecheck passed. These do not substitute for the still-pending real
  PostgreSQL/API review and snapshot-replay tests.

### Follow-up — bind cast review drafts to both Wikidata source snapshots (7 November 2026)

- Closed a provenance gap in the review-only cast-candidate pipeline. Each
  draft now binds the actor identity to its exact retained Wikidata
  EntityData URL, entity label, revision, license and snapshot SHA-256, and
  binds the film-side `P161` cast references to the exact retained film
  EntityData revision/hash. The candidate report, capture manifest and
  credit-target manifest must match their recorded byte hashes and frozen
  selection before draft creation. Replay validation checks that the referenced
  statement locators/revisions/hashes agree. The draft remains
  `review_required`; actor identity and cast-label matches do not prove an
  actor-character credit.
- Regenerated new immutable, local-only bundles without replacing prior
  artifacts: first ten = 181 drafts from 221 candidates, 40 excluded;
  ranks 11–100 = 1,365 drafts from 1,823 candidates, 458 excluded. The
  combined 100-film audit validates against the actual frozen English pilot
  manifest (not the separate multilingual top-100 file): 2,044 candidate rows,
  1,546 same-film identity drafts, 458 unresolved names, 40 identity-only
  suggestions and 52 quarantined spans. All 1,546 drafts remain review-only;
  no operational assertions or working-corpus rows were written. JSON and
  passage-free review sheet are local at
  `data/evaluation/catalog-intake/english100-pilot-v1/cast-candidate-coverage-v3.json`
  (SHA-256 `64479b030fbf80863f1d46808609436c6909b21ae6d3c7a82eba678c1e323db6`)
  and `cast-candidate-review-v3.md` (SHA-256
  `8d83239293c4f1955c08e2b35add17ea2047ad7f790d280c035684669926aa08`).
- The offline coverage checker now accepts the real pilot manifest's nested
  `catalog_candidates` form only when there is exactly one canonical QID; it
  rejects ambiguous rows instead of choosing. Tests also caught and fixed a
  locator-variable collision in replay validation. The focused pure suites
  pass **49/49**; the full non-integration backend suite passes **417**, with
  **83 skipped**. Frontend tests pass **5/5**, TypeScript checking and
  production build pass, and `git diff --check` is clean.
- The real PostgreSQL/API test gate is still pending. The Docker listing shows
  the isolated database and API containers up, but the project integration
  runner cannot inspect the migration image because Docker Desktop's containerd
  blob store returns `input/output error`. The existing API image has no source
  bind mount, so it cannot validate the current code. No migration, test seed,
  working-corpus database query or write was performed in this attempt; port
  5432 and the working DB remain out of scope. Keep the persistence/API changes
  uncommitted and unpublished until the current code passes the isolated
  `cinegraph_test` migration, replay, review, and route-authorization tests.

### Follow-up — verify the retained Wikidata person payloads before drafting (7 November 2026)

- Tightened the actor identity binding one step further: the source-statement
  builder now checks the exact candidate-bound credit-label checkpoint bytes,
  its captured record for each actor QID, and the retained EntityData payload
  bytes themselves. It verifies payload SHA-256, entity QID, `lastrevid`, and
  that the candidate's English label is present as the entity's English label
  or alias. The film `P161` source revision/hash remains independently bound
  through the captured film manifest and target locators. Missing or altered
  actor snapshots fail closed and cannot produce drafts.
- The offline CLI resolves checkpoint paths beneath each local evaluation
  partition and rejects symlinks, traversal and escaped paths. The combined
  review audit also checks that each statement bundle records the exact
  candidate-bound person-label checkpoint hash.
- Created fresh immutable outputs; prior v3/v4 bundles remain intact. The
  first-ten v4 bundle has 181 drafts (SHA-256
  `53cf15452b5dac955034c6a1d7bd87c7ca8fd6eb774f46b11d402490babf9095`); the
  rank 11–100 v5 bundle has 1,365 (SHA-256
  `dbf89bf53fb4d5402125fc12602c29529c64f8056ffda3f6475dcad80e6db520`). The
  refreshed 100-film audit remains 2,044 candidates, 1,546 review-only exact
  identity drafts, 458 unresolved names and 52 quarantined spans. Its JSON is
  `data/evaluation/catalog-intake/english100-pilot-v1/cast-candidate-coverage-v4.json`
  (SHA-256 `f0e2198341a28329c4c1f3f4944c54e46cefa372e1ae8d69dbb066b21fedd6e8`);
  the companion passage-free review sheet is `cast-candidate-review-v4.md`
  (SHA-256 `dd1db1429439caa50c610375922dad8decc06c7899bca909484073c51d5d05cb`).
- Focused source-binding, candidate and coverage tests now pass **50/50**.
  The full backend non-integration suite passes **418**, with **84 skipped**.
  This remains offline provenance validation only: no production assertions,
  rights approvals, corpus updates or embeddings were created. Real
  PostgreSQL/API review integration is still blocked by the local containerd
  image-blob I/O error documented above; do not treat passing unit tests as a
  substitute for that gate.

### Follow-up — preserve independent support when reviewing cast assertions (7 November 2026)

- Hardened approval against duplicate operational facts: when exactly one
  active, source-fact `cast` assertion already matches the same film, person
  and actor-character value, approval reuses it and adds the candidate's own
  `AssertionEvidence` link. Multiple matching assertions fail for explicit
  review rather than choosing arbitrarily.
- A later rejection or deferral now retracts the reused assertion only when
  this candidate is its sole evidence. Independent evidence—including evidence
  not represented by a `SourceAssertion`—keeps the fact active. The candidate's
  decision and provenance remain auditable either way.
- Added an isolated PostgreSQL integration case for reuse, evidence attachment
  and rejection with independent support. It compiles, but has not yet run:
  Docker's migration-image blob read fails before the integration stack can be
  rebuilt. Full offline backend suite remains **418 passed, 84 skipped**; the
  new DB behavior is not declared verified until that test runs in
  `cinegraph_test`.
- Also tried a one-shot test container from the already-running integration API
  image with the repository mounted read-only. Container startup failed on a
  different missing containerd blob with the same `input/output error`, before
  Python or PostgreSQL tests started. No temporary schema or database
  statements were created; the test volume and working database remain intact.

### Follow-up — reproduce the offline audit and recheck current test gates (7 November 2026)

- Re-ran the full offline backend suite from the configured `cine-graph` Conda
  interpreter with the repository's vendored parser fallback: **418 passed,
  84 skipped**. The skipped cases are PostgreSQL/API integration tests and do
  not validate migrations or persistence behavior.
- Re-ran frontend unit tests (**5/5**), TypeScript checking and the production
  Next.js build; all passed. `git diff --check` is clean.
- Rebuilt the English-100 cast coverage and review sheet into temporary files
  under the ignored local evaluation partition, then compared SHA-256 against
  the retained v4 outputs. Both matched exactly: coverage JSON
  `f0e2198341a28329c4c1f3f4944c54e46cefa372e1ae8d69dbb066b21fedd6e8`, review
  sheet `dd1db1429439caa50c610375922dad8decc06c7899bca909484073c51d5d05cb`.
  The verified summary remains 100 films, 2,044 candidate rows, 1,546
  review-only drafts, 458 unresolved names and 52 quarantined spans; it still
  explicitly reports `actor_character_credits_verified: false` and
  `operational_assertions_written: false`. Temporary comparison files were
  removed; evaluation data remains local and ignored by Git.
- The isolated integration API is currently not listening on `127.0.0.1:18001`.
  This shell also receives permission denied when connecting to the Docker
  socket, so it cannot start the isolated stack. No Docker storage repair was
  attempted; the working catalog database was not queried or changed. The new
  review/replay persistence tests remain unverified until the migration and
  tests run against the dedicated `cinegraph_test` database.
- Additional offline check: Alembic successfully rendered the full PostgreSQL
  migration chain to SQL through revision `20261107_21`, including the cast
  decision constraints and append-only trigger. This checks migration
  generation only, not execution. An elevated run of the repository's
  integration script still fails before service startup because Docker
  containerd cannot read image blob
  `2453265d3c53f8001baf3f56066dfc2d4eba9b58bc32eb619b4316694fc047d3`
  (`input/output error`). No integration seed or test query ran.
- A second assertion-preservation edge case was found during code review: an
  active assertion may carry independent `source_id`/URL/revision provenance
  without a separate `AssertionEvidence` row. Rejection or deferral now keeps
  that assertion active whenever its stored source reference differs from the
  candidate being reviewed. Added a PostgreSQL regression test for this
  source-provenance-only case. Also hardened the offline cast-draft validator
  to fail closed on malformed (non-string) actor identity labels rather than
  raising a type error. The full offline suite now passes **420 tests**, with
  **85 integration/environment-dependent tests skipped**. The new database
  regression is among those skipped pending a working test stack.
- The append-only decision table now also enforces a non-blank reviewer at the
  PostgreSQL constraint layer, matching API validation. Alembic's offline SQL
  renderer includes the named check. Its direct DB rejection test is included
  in the isolated API integration suite and remains unexecuted until
  `cinegraph_test` is available.
- Preserved the verified offline-only source identity hardening in local commit
  `e3223eb` (`Harden cast source identity validation`); it contains only the
  validator and its pure unit tests. It has not been pushed. The review schema,
  API, UI and their PostgreSQL tests remain separate and uncommitted pending
  the isolated database gate.

### Follow-up — publish offline cast coverage audits and recheck the DB gate (7 November 2026)

- Added and tested a reusable crosswalk/coverage audit slice that binds
  Wikipedia actor-role candidates to exact retained passages and Wikidata
  `P161`/`P453` statements, and refuses mismatched source manifests. Its
  focused deterministic tests pass **15/15**; the complete backend
  non-integration suite passes **406 tests** with **99 integration cases
  deselected**. No retained corpus or source assertions were modified.
- Committed as `2a37d6b` (`Add source-bound cast coverage audits`) and pushed
  to `origin/main`, together with the already committed offline audit/source
  history. The uncommitted database review migration, API and UI were excluded.
- Rechecked the isolated database gate. Compose cannot inspect its pgvector
  image because Docker Desktop reports a containerd blob-store I/O error; a
  direct probe reports the existing `cinegraph-integration-db-test-1` is not
  running, and isolated PostgreSQL tests fail to connect to `127.0.0.1:5433`
  (`connection refused`). Thus the nine cast-review/replay integration cases
  remain unverified; these are infrastructure connection failures, not
  passing application tests. The working catalog database was not accessed.
- Frontend unit tests pass **5/5**, TypeScript and production build pass.
  `npm run lint` is currently invalid because its script invokes the removed
  `next lint` command; replace it with the supported project lint command when
  linting is restored. `git diff --check` passes.
- Current evidence still shows zero of 200 narrative snapshots approved for
  semantic indexing and zero of 7,466 stored vectors eligible under the
  snapshot-purpose gate. This blocks any claim that the existing embeddings
  are currently cleared for product retrieval; rights decisions must be
  explicitly reviewed and recorded.
- Spot-checked the exact crosswalk rows for *The Dark Knight*: it has 9 direct
  Wikidata `P161`/`P453` links aligned to retained Wikipedia cast passages;
  5 are exact English-label agreements. The other 4 illustrate why string
  matching is not approval (for example, `Bruce Wayne / Batman` versus
  `Bruce Wayne`, and `James "Jim" Gordon` versus `Jim Gordon`). All 9 remain
  `review_required`; the crosswalk remains corroboration for a human, not a
  claim that the film's complete cast/character mapping has been verified.

### Follow-up — unify narrative-use eligibility checks (7 November 2026)

- Audited the end-to-end snapshot-purpose gate. Preprocessing already rejected
  missing approval, unsupported license and absent attribution, and the shared
  query required the latest approved decision with a basis URL and rationale.
  However, the query used by retrieval, comparisons, indexing and synthesis did
  not itself recheck snapshot license or attribution URL shape. That left the
  read boundary relying on chunks having been created only by today's
  preprocessor.
- Centralized the pure policy so approval, eligible license, HTTPS attribution,
  HTTPS basis URL and rationale are checked together by both preprocessing and
  the intake readiness preview. Extended the shared PostgreSQL retrieval scope
  to recheck the snapshot license and HTTPS host shape for both attribution and
  decision basis on every read; this protects older or manually materialized
  chunks as well as newly built chunks. Updated the offline catalog readiness
  reporter to use the same policy.
- Added pure policy cases and a PostgreSQL integration fixture covering one
  eligible item and six fail-closed cases, including a later denial, a
  hostless HTTPS basis and credential-bearing URLs. The PostgreSQL test is
  written but remains unexecuted because this environment cannot access the
  Docker socket for the isolated test database. The complete backend suite
  passes **421 tests**, with **86 integration/environment-dependent tests
  skipped**; the focused rights, scope SQL and readiness tests pass **17/17**.
  Python compilation and `git diff --check` pass. No working corpus, snapshot,
  chunk or vector was modified.

### Follow-up — cast-review delivery and isolated database gate (7 November 2026)

- Continued the cast-credit correction path with an append-only review decision
  table, a source-bound local operator queue, and projection into the existing
  `Assertion`/`AssertionEvidence` model. Approval revalidates the retained
  Wikipedia snapshot checksum, exact passage locator and text, CC BY-SA
  attribution, canonical film/person IDs, and the pinned Wikidata identity and
  film-cast statement evidence. Reject/defer stays source-only unless an
  existing assertion is supported only by this candidate; independent support
  is preserved. No second graph/fact table was added.
- The local review page presents the exact quote and source revision, actor
  identity cross-check, statement locators, hashes and rationale before a
  decision. The film profile consumes credits through the existing sourced
  credit read model. Strengthened the PostgreSQL test to assert that an
  approved actor-character credit appears in that UI-facing read model with
  its source URL. This test is written but cannot yet be executed.
- Offline validation: full backend suite **421 passed, 86 skipped**; frontend
  tests **5/5**, TypeScript and production build pass; changed Python modules
  compile; Alembic renders the full migration chain through `20261107_21`.
  These checks do not prove schema execution, persistence behavior, or the
  browser flow against a live seeded API.
- Rechecked only the isolated integration stack. The API container's health
  endpoint returns `ok`, but inspection shows the `cinegraph_test` database
  container is stopped (`running=false`, exit code 133). Its existing
  container cannot start because Docker reports an I/O error reading its
  container `hosts` file; Compose also fails reading the pgvector image blob.
  Port 5433 is not listening. No migration, seed or test DB query ran, and the
  working catalog database was not accessed. Do not treat the API health
  response as proof that the integration service is usable.
- The cast-review migration/API/UI and its PostgreSQL tests remain local and
  uncommitted pending the real database and API contract gate. The local rights
  boundary commit `334609b` is also not pushed until that PostgreSQL test can
  run. User-local `.agents/` and `.codex/` remain untouched and unstaged.

### Follow-up — bind each cast draft to its exact candidate row (7 November 2026)

- Strengthened the offline 100-film coverage checker beyond equal per-film
  counts: every review-only statement draft must now match one exact
  same-film candidate across actor/film IDs, actor and character labels,
  article revision/hash, passage locator/hash and excerpt, Wikidata person
  snapshot and cast-statement locators, and label-only character suggestions.
  Text fields use the same surrounding-whitespace trim as the statement
  builder; other values remain exact. A regression case proves that a
  syntactically valid, content-addressed draft with a different role is
  rejected even when the candidate and statement manifests are re-bound.
- Revalidated the retained first-ten and ranks-11–100 inputs against the
  frozen English-100 manifest. All **1,546/1,546** candidate/draft bindings
  match; the 100-film summary remains 2,044 candidates, 458 unresolved source
  names and 52 quarantined spans. The regenerated v5 JSON and review sheet are
  byte-identical to v4 (same SHA-256), confirming that the stricter validator
  did not alter the retained review queue. Outputs remain local under ignored
  `data/evaluation/`; no source facts or corpus rows were written.
- The complete offline backend suite passes **422 tests**, with **86
  PostgreSQL/API integration cases skipped**. This does not validate the
  pending cast-review migration, API persistence or browser flow; those still
  require the isolated `cinegraph_test` stack. `git diff --check` is clean.

### Follow-up — expose both Wikidata cast-evidence chains in review (7 November 2026)

- The local cast-review queue now returns the captured film-side Wikidata
  `P161` source metadata and individual statement references in addition to
  the actor identity snapshot. The operator page links both exact captured
  revisions and displays their hashes/locators next to the retained Wikipedia
  passage. This makes the cross-check available to a reviewer without
  conflating cast membership with evidence of an actor-character pairing.
- Added integration assertions for the film QID, revision and P161 reference
  payload. The test is written but still awaits the isolated PostgreSQL/API
  gate. Frontend tests pass **5/5**, TypeScript check and production build pass;
  full offline backend suite passes **422 tests**, with **86 integration tests
  skipped**. The integration runner still fails before startup on Docker's
  pgvector image-blob I/O error, so no live queue response or browser flow is
  claimed as verified.
- Added `*.tsbuildinfo` to `.gitignore` after the TypeScript check generated a
  local compiler cache; removed that generated artifact from the worktree.

### Follow-up — verify cast cross-checks from retained Wikidata bytes (7 November 2026)

- Audited the approval boundary after exposing both cited Wikidata evidence
  chains in the review page. The draft validator checked QIDs, revision/hash
  shapes, P161 locator strings and internal cross-references, but approval did
  not prove that those exact Wikidata snapshots still existed or that the
  captured film bytes actually contained the cited P161 actor statement.
- Approval and queue eligibility now resolve an exact successful CC0 Wikidata
  `SourceSnapshot` by source, QID, entity URL, EntityData capture URL, revision,
  hash and attribution. They read the retained local bytes once, verify size
  and SHA-256, confirm the entity/revision and actor label, then confirm every
  cited `claims.P161[n]` locator names the candidate actor. No live request is
  made. The queue reports missing or inconsistent cross-check bytes as
  `source_evidence_invalid` and disables approval; the write path repeats the
  same validation before recording a decision or projecting an `Assertion`.
- Added pure policy cases for exact P161 membership, absent locators,
  non-value statements, malformed locators and a different actor. Updated the
  PostgreSQL integration fixture to retain small local Wikidata EntityData
  payloads and added a regression case proving a missing film snapshot blocks
  both approval and operational assertion creation.
- Verification: offline backend suite **415 passed, 102 integration tests
  deselected**; Python compilation and `git diff --check` pass. Frontend tests
  **5/5**, TypeScript check and production build passed earlier in this same
  work session (no frontend files changed afterward).
- Attempted `backend/scripts/run_integration_tests.sh` with the isolated
  `cinegraph_test` stack. Docker failed before Compose startup while reading a
  local containerd image blob (`input/output error`); migrations, fixture seed
  and integration queries did not run. No working-corpus database or retained
  film data was accessed. The database/API gate is still outstanding, so this
  change remains local and uncommitted.

### Follow-up — browser-check the cast-review first-use flow (7 November 2026)

- Added a Playwright check for the cast-review desk's first-use state: page
  heading, operator email field, explanation that Wikidata identity/cast
  membership are cross-checks rather than character-credit proof, and return
  navigation. Constrained the E2E Next.js server to `127.0.0.1` rather than
  binding all interfaces. The focused test passed **1/1** in the already
  installed Google Chrome; no browser download, API call or DB write was used.
- Re-ran frontend unit tests (**5/5**), TypeScript and production build; all
  pass. Re-ran the offline English-100 source replay; the captured inputs still
  validate to combined digest
  `835bf314ff069248e3a24af9a30133fd916b13a39a10a77e30dede6d1bb2408f`.
  This certifies retained byte/identity consistency only, not rights approval,
  database ingestion or semantic quality.
- The existing `cinegraph_test` DB and API containers report healthy status and
  the API health route responds, but the DB has no host port mapping and
  container exec fails with the same containerd blob `input/output error`.
  Compose cannot inspect/rebuild the migration image for that reason. The
  running API image predates these local changes; no latest-code database/API
  or full browser integration test has run. No migration, seed, working-corpus
  query or corpus mutation occurred.
- Rechecked the current gates: offline backend **415 passed, 102 integration
  tests deselected**; frontend unit tests **5/5**, `tsc --noEmit`, and the
  production build pass. `git diff --check` is clean. Docker Desktop 4.86 still
  reports the isolated DB container healthy and the stale API container up,
  but `docker image ls` fails while reading containerd blob
  `b049884f3a932945e6d8b7e67068f158e0550134729c07fed01ae82d13d5dd7a`
  (`input/output error`). No host PostgreSQL/pgvector installation is
  available as a separate test path. These are offline/UI-build results only;
  schema execution, cast-review persistence and current-code API behavior
  remain unverified. No container, volume, or working-corpus database was
  modified.

### Follow-up — recheck offline and isolated database gates (7 November 2026)

- Re-ran the full offline backend suite against the current worktree with the
  repository's retained `mwparserfromhell` dependency on `PYTHONPATH`:
  **415 passed, 102 integration tests deselected**. Focused cast review and
  cast-candidate coverage policy tests pass **13/13**. Frontend unit tests pass
  **5/5**, `npx tsc --noEmit` passes, and `npm run build` completes with the
  current admin cast-review routes included.
- Re-attempted `backend/scripts/run_integration_tests.sh` against its explicitly
  isolated `cinegraph_test` compose project. The Docker daemon is reachable,
  but Compose cannot read the cached `pgvector/pgvector:pg16` image blob
  (`sha256:a3625087…`, input/output error) before starting the test stack. The
  currently running default `aarambham` API and database both report
  unhealthy; they were not restarted, queried, or used for tests. No test
  migration, fixture seed, or database query ran.
- This confirms the earlier local-only checks but does not close the database
  gate: cast-review persistence, migration execution, API contract behavior,
  and the current-code browser flow remain unverified. All work remains local;
  no source/corpus data or Docker volumes were changed.

### Follow-up — reproduce English-100 cast source audits (7 November 2026)

- Rebuilt the cast-candidate coverage from the retained first-ten and ranks
  11–100 source reports, exact-input statement manifests and frozen English-100
  pilot. The validator accepted all 100 identity/source bindings, and the
  generated JSON and passage-free review sheet are byte-identical to the
  existing v5 artifacts (SHA-256 `f0e2198341a28329c4c1f3f4944c54e46cefa372e1ae8d69dbb066b21fedd6e8`
  and `dd1db1429439caa50c610375922dad8decc06c7899bca909484073c51d5d05cb`).
  Totals remain 2,044 extracted candidate rows, 1,546 exact actor-identity
  candidates still requiring review, 458 unresolved names, 52 quarantined
  spans and 324 label-only character suggestions. No candidate was promoted.
- Rebuilt the crosswalk from exact retained Wikipedia passage derivatives,
  Wikidata film/person captures, candidate reports and captured English
  labels. The JSON and Markdown are byte-identical to the existing v1 report.
  It finds 521 direct `P453` character qualifiers across 509 candidate actors;
  324 have exact English-label agreement. All 521 remain `review_required`;
  a Wikidata qualifier and label match are corroboration, not independent
  proof that the article credits that performer with that character.
- Re-ran the cast-review desk's empty-state Playwright test in the installed
  Google Chrome: **1 passed**. It checks that the page explains the evidence
  boundary before an operator enters an email; it does not load candidates,
  exercise authorization or verify API/database behavior. The first attempt
  could not bind localhost in the sandbox, and the default Playwright browser
  binary is absent, so the successful run explicitly reused installed Chrome.
- Rechecked the Docker discrepancy directly: although `compose ps` displayed
  the stale database container as healthy, `docker inspect` reports it exited
  with code 133 and an I/O error reading its `hosts` file; port 5433 is closed.
  The old test API's `/health` response is not a DB health check. No containers
  were restarted, and no test or working-corpus database was queried.
- Attempted an additive `docker pull pgvector/pgvector:pg16` to refresh the
  test image without removing containers or volumes. Docker failed before
  downloading layers because its containerd metadata database (`meta.db`)
  itself returns an input/output error. No further Docker storage repair,
  restart, prune or volume operation was attempted; database execution remains
  blocked on Docker Desktop storage recovery.

### Follow-up — count synopsis headings as plot evidence (7 November 2026)

- A fresh replay of the retained English-100 capture audit found that
  *Hamilton* (`Q84323848`) had 9 extracted `Synopsis`, `Synopsis / Act I`, and
  `Synopsis / Act II` passages, but `catalog_pilot_audit.section_categories`
  classified plot only when the heading literally contained “plot.” The
  shared passage coverage policy already recognizes “synopsis” and “story.”
- Aligned the pilot audit with that existing policy and added regression tests
  for `Synopsis`, nested `Synopsis / Act I`, and `Story` headings. Re-audited
  both exact retained capture batches: first 10 passed **10/10**, ranks 11–100
  passed **90/90**; both now report **0 plot gaps** and **0 production gaps**.
  The resulting English-100 heading inventory is **100/100 plot-section
  present**; this is source-heading availability, not semantic adequacy or
  answer support. No raw source, identity, assertion, passage or vector was
  changed. These are local retained-capture results only: the capture bundle
  has not been replayed into the working catalog, so the older DB-backed
  readiness report remains a historical snapshot and must not be silently
  updated to 100/100.
- Saved new local-only audit versions at
  `data/evaluation/catalog-intake/first10-v1/capture-audit-v10.md` and
  `data/evaluation/catalog-intake/english100-rank11-100-v1/capture-audit-v4.md`.
  Full offline backend suite: **415 passed, 102 integration tests deselected**.
  This correction is independent of the still-unavailable PostgreSQL/API gate.

### Follow-up — make passage-length review flags traceable (7 November 2026)

- The v2 capture audit counted passages under 80 characters and over 2,500,
  but it did not identify their source section or ordinal. Added audit schema v3
  with passage-free review flags containing film/QID, normalized section
  locator/title, ordinal, character count, flag kind and content SHA-256. The
  audit Markdown and combined reconciliation render those locators and hashes;
  they never copy passage prose, and no short/long passage is automatically
  discarded. The reconciler now emits v2 and accepts historical v2 capture
  audits as well as v3.
- Re-audited the retained first-ten and ranks 11–100 captures from immutable
  local bytes: **10/10** and **90/90** identities/integrity, respectively;
  combined **100/100**, **3,694 passages**, **6 under 80 characters**, and
  **2 over 2,500 characters**. The six short flags resolve to identifiable
  quote/cast/plot/release/award passages; the two long flags are coherent
  production/reception passages suitable for downstream chunking. These are
  inspection outcomes, not semantic-quality or ingestion approval. The local
  versioned reports are `first10-v1/capture-audit-v11.md` and
  `english100-rank11-100-v1/capture-audit-v5.md`; snapshots and prose remain
  ignored local data.
- Added the offline `backend/scripts/reconcile_english_catalog_pilot.py`
  command so the exact source captures can be reconciled into deterministic,
  immutable local JSON and Markdown reports without a database or network.
  Replayed it to produce
  `data/evaluation/english100-capture-reconciliation-v7.json` and `.md`.
  Existing v5 artifacts were schema-v1 historical reports, so the command
  correctly refused to overwrite them and wrote a new version instead.
- The Markdown now includes a film-by-film matrix of value-bearing Wikidata
  statement counts and Wikipedia section passage counts. This makes missing
  metadata visible per title while keeping prose and unreviewed raw values out
  of the report. The matrix describes source coverage only, not verified facts.
- Focused capture/reconciliation tests: **23 passed**. Full offline backend:
  **417 passed, 102 integration tests deselected**. The isolated PostgreSQL
  integration gate remains unavailable due to the previously documented
  Docker/containerd I/O failure; this report-only change does not claim to
  close it. No database, raw source, vector, container or volume was changed.

### Follow-up — let operators disposition quarantined cast evidence (7 November 2026)

- Read-only review of the in-progress cast-review endpoint found that the UI
  enabled reject/defer for blocked rows while the service ran the full approval
  validator for every decision. This made it impossible to record a reason for
  malformed or checksum-failing evidence, contrary to the quarantine workflow.
- Changed the boundary so approval still requires exact Wikipedia snapshot,
  passage, actor identity and film P161 checks; reject/defer now require only a
  review-required cast source assertion attached to the English Wikipedia
  source. A bad checksum can therefore be dispositioned without projection.
  A candidate evidence link resolving to multiple Assertions now fails closed
  instead of updating an arbitrary projection. Added a real-PostgreSQL test
  covering failed-approval plus durable reject/defer decisions and zero facts.
- The full offline suite still passes: **417 passed, 104 integration tests
  deselected**. Alembic generated the complete upgrade SQL through
  `20261107_21` without connecting to a database. SQL generation checks
  revision wiring and rendering only; it does not replace applying the
  migration or running the persistence test against `cinegraph_test`.
- This behavior is not yet verified: the isolated integration runner still
  cannot read Docker's cached pgvector blob
  `sha256:a3625087…` (containerd input/output error). No container, volume,
  production corpus or database was touched. The new cast-review edits remain
  local and uncommitted until that integration test and migration pass.
- A fresh retry on the same day now fails earlier while Compose reads the
  existing migration image blob `sha256:e166e4b1…` (also containerd
  input/output error). `compose ps` shows the old isolated DB as healthy, but
  it has no host port mapping; the old API container is not a valid test runner
  for current code (even a read-only Python probe returns I/O error). No
  container, volume, or database was restarted or altered.
- The current Chrome browser test for the cast-review first-use state passes
  **1/1** against the local Next page: it verifies the evidence-boundary copy,
  configured-email prompt and navigation. This does not authenticate an
  operator, load the queue or exercise API/database decisions.
- A follow-up UI review found that a failed queue request or changing the
  configured email could leave previously loaded candidates visible. The
  cast-review page now clears stale rows on identity changes and failed
  responses, and ignores out-of-order queue responses. Frontend tests pass
  **5/5**, TypeScript checking and the production build pass, and the targeted
  Chrome first-use test passes **1/1**. No live queue request was made.
- Re-ran the full offline backend suite with the project Conda interpreter:
  **417 passed, 104 integration tests deselected**. The first attempted command
  accidentally resolved to system Python; it was discarded as an environment
  error and the suite was rerun successfully with the explicit
  `cine-graph` interpreter.
- Re-attempted the repository integration runner with authorized Docker access.
  It still fails before Compose startup because Docker cannot read cached
  pgvector blob `sha256:a3625087…` (input/output error). No containers,
  volumes, migrations or databases were changed by that failed attempt. Cast
  persistence/API behavior remains unverified and the work stays uncommitted.

### Follow-up — retain identity-only cast suggestions without overstating them (7 November 2026)

- The first 100 English pilot had 40 exact, unique matches between a Wikipedia
  cast-page name and a retained Wikidata English person label/alias that were
  excluded only because the captured film entity did not list the person in
  `P161`. These are now kept as **identity-only review suggestions**, with no
  fabricated film-side cast evidence. The review UI and audit sheet explicitly
  warn that this identity match is not cast corroboration; the reviewer must
  inspect and approve the exact Wikipedia credit before an operational
  assertion can exist.
- The additive v4 draft schema binds the exact English label/alias and person
  snapshot, the film identity snapshot, the retained article passage and an
  explicit identity-resolution basis. Replay validates these fields; approval
  confirms the actor is absent from the captured film `P161` list and verifies
  the source name against the captured label/alias. Existing same-film `P161`
  candidates still require their exact statement references. Neither path
  silently writes a fact.
- Rebuilt the immutable local 100-film review report as
  `data/evaluation/catalog-intake/english100-pilot-v1/cast-candidate-coverage-v8.{json,md}`.
  It reports 2,044 candidate spans, 1,546 same-film identity candidates, 40
  identity-only suggestions (all 40 have review-only drafts), 458 unresolved
  source names, 52 quarantined spans and **1,586 review-only drafts**. All 100
  films remain in scope; no operational assertions were created. The report
  is local/ignored and carries its source and manifest fingerprints.
- Added an isolated PostgreSQL integration case for reviewing an exact alias
  match when the retained film `P161` snapshot has no such actor. It verifies
  the queue marks it as identity-only, exposes no film-cast evidence, and only
  creates a sourced credit after explicit approval. Python compilation and
  focused pure suites pass (**35 passed**); the full offline backend suite
  passes (**425 passed, 105 integration cases deselected**). Frontend tests
  pass (**5/5**), TypeScript checking succeeds and the production build
  completes. The current Chrome first-use browser test for the local cast
  review page also passes (**1/1**); it does not submit a review or load the
  database-backed queue. The new integration case is not claimed as passing: a fresh
  isolated-run attempt still fails before Compose startup because Docker
  cannot read the cached pgvector image blob (`sha256:a3625087…`, input/output
  error). No containers, volumes, migrations or databases were changed. No
  working-corpus rows or external files were touched.

### Follow-up — expose the exact film snapshot behind identity-only review (7 November 2026)

- Review of the source-backed queue found that identity-only approval checked
  the retained film Wikidata snapshot for absence of the actor from `P161`, but
  the operator could not open that exact film revision from the review card.
  The API now returns this already-bound snapshot metadata; the UI links the
  captured EntityData revision and Wikidata item and displays the snapshot
  revision, license and SHA-256 beside the explicit “not cast corroboration”
  warning. This lets the reviewer inspect the same record the approval policy
  actually validated.
- The integration case asserts the exact film identity snapshot is exposed.
  While checking this fixture, replaced a stale hard-coded reference hash with
  the real hash computed from the retained fixture bytes. This previously
  unexercised assertion would otherwise have failed when the integration suite
  becomes runnable.
- Verification after the change: **425 offline backend tests passed**, frontend
  tests **5/5**, TypeScript and production build passed, and the cast-review
  first-use Chrome test passed **1/1**. The integration suite remains blocked
  before startup by the existing Docker image-blob I/O error. Read-only Docker
  inspection shows the stale `api-test` is up but the old `db-test` has no host
  port mapping. The old API returned a healthy response through an approved
  localhost check, but its image predates the current work and cannot verify
  current-code persistence; a read-only `docker compose exec` probe failed with
  the same container I/O error. I did not restart, replace, seed or alter those
  containers or their volumes, and did not use them as evidence for
  current-code persistence behavior.

### Follow-up — align replay regression fixtures with cast-draft v4 (7 November 2026)

- The database replay test still asserted the old v3 extractor string, so it
  would fail after the v4 identity-basis schema change even if persistence
  worked. It now checks the service's current extractor version. Added an
  isolated-database replay case for a uniquely matched English alias: the
  assertion keeps `review_required`, has no P161 locators or film-cast
  evidence, and creates no operational `Assertion`.
- Exercised the new identity-only replay fixture through the real offline
  manifest builder and draft validator; it validates as v4 with basis
  `exact_unique_english_alias`. The complete offline backend suite passes
  **425 tests**; **106 integration cases are deselected**. The extra deselected
  case is the new PostgreSQL replay test, not a pass. The Docker/containerd
  image-read failure remains the reason it cannot yet be executed against
  `cinegraph_test`.

### Follow-up — keep the cast review reader on the current draft version (7 November 2026)

- A cross-file version audit found the review queue and decision validator still
  pinned to the v3 cast-draft extractor, while the current builder/replay
  validator emit v4. That would hide every new v4 candidate from the review
  queue and reject its decisions. The review service now imports the shared
  source-statement property and extractor constants, eliminating the duplicate
  stale values.
- Added a regression test asserting that the review reader's supported
  extractor matches the draft builder. The full offline backend suite passes
  **426 tests**, with **106 PostgreSQL integration tests deselected**. This
  catches the version mismatch without claiming the database queue or review
  transaction has passed; those still require the isolated DB gate.

### Follow-up — verify the declared label-versus-alias resolution basis (7 November 2026)

- Tightened identity-only matching so the recorded basis must match the exact
  captured Wikidata name that matched the Wikipedia cast name: canonical
  English label or English alias. The same pure policy is now used when the
  draft is built and again when a reviewer approves it. A candidate cannot say
  “label” when only an alias matched, or vice versa.
- Added regressions for label/alias/unmatched cases and for rejecting an
  alias mislabeled as an exact English-label match. Focused source/review
  policies pass (**36 passed**); full offline backend passes (**428 passed,
  106 PostgreSQL integration tests deselected**). The isolated stack remains
  unchanged from the previous check: stale containers, no DB host port, and a
  corrupted cached image prevent running current-code persistence tests.

### Follow-up — add an HTTP contract for cast-review decisions (7 November 2026)

- Added an API/PostgreSQL integration contract that creates a uniquely bound
  Wikipedia source candidate inside `cinegraph_test`, rejects an unauthorized
  operator and malformed rationale, then records rejection and deferral via
  the real HTTP route. It verifies reviewer attribution, null fact projection,
  monotonically increasing decision versions, and the persisted append-only
  history. The candidate has a retained source snapshot but no canonical film
  or person identity, so this contract cannot accidentally publish a credit.
- Verified Python compilation, `git diff --check`, and the complete offline
  backend suite (**428 passed, 107 integration tests deselected**). This new
  HTTP contract is among the deselected tests and is not yet verified against
  a live API/test database. The isolated Docker image I/O issue remains an
  explicit unresolved gate; no integration database or container was changed.

### Follow-up — fail closed before showing cast evidence in the review queue (7 November 2026)

- A source-chain audit found the operator queue checked candidate structure and
  retained Wikidata identities, but unlike approval it did not verify the
  retained Wikipedia bytes, snapshot rights/attribution or exact passage before
  returning the candidate quotation. The queue now runs the same immutable
  source and passage validation as approval, and returns no quote when a
  candidate is blocked. The UI omits an absent quote and retains the explicit
  block reason and pinned revision link.
- Added isolated DB and API-contract regressions for altered source bytes and
  missing canonical identities: neither may expose the candidate phrase as
  verified evidence. All integration modules collect (**44 collected**) and
  Alembic reports the new migration `20261107_21` as its sole head; collection
  does not execute DB tests. Static compilation and whitespace checks pass. Full
  offline backend remains **428 passed, 108 integration tests deselected**;
  frontend is **5/5 tests**, TypeScript passes and production build succeeds.
- Rechecked the integration environment read-only. Docker shows the dedicated
  database container healthy but without the declared host port mapping;
  inspecting its image still fails reading its pgvector content blob with an
  I/O error. A read-only connection attempt to the explicitly named
  `cinegraph_test` database on localhost:5432 also failed before returning a
  SQL result (`global/pg_filenode.map`: input/output error). No SQL mutations,
  repairs, restarts, volume operations or access to the working corpus were
  performed. The new DB/API regressions remain unexecuted.

### Follow-up — harden structured-metadata coverage and rerun the frozen pilot (7 November 2026)

- The offline Wikidata audit treated malformed nested `mainsnak` / qualifier
  values as valid coverage and could raise on malformed claim shapes. It now
  counts only value-bearing snaks, validates character-entity qualifiers and
  release precision shapes, and safely ignores malformed claim/qualifier
  containers. The report schema is v4; the reconciler accepts v2/v3 historical
  audits and v4 current audits.
- Audit Markdown output now chooses the next immutable per-bundle version and
  uses the repository's no-overwrite writer. It does not replace prior audit
  results. Regenerated local-only reports are
  `first10-v1/capture-audit-v12.md` (**10/10**, 484 passages) and
  `english100-rank11-100-v1/capture-audit-v6.md` (**90/90**, 3,210 passages).
  Both pass source hash, identity, revision and deterministic parser checks.
- Reconciliation against the frozen English-100 pilot passes **100/100** with
  3,694 verified passages. All 100 have captured plot and production sections;
  themes/analysis is present for 43 and legacy/influence for 50. The stricter
  parser preserved the current observed counts: 2,541 Wikidata cast statements
  total, 1,270 with a valid character qualifier, and 395 territory-qualified
  release-date statements. These are source-coverage counts, not accuracy or
  completeness claims.
- Focused audit/reconciliation tests pass **25/25**; the complete offline
  backend suite passes **430 tests**, with PostgreSQL integration tests
  deselected. No source snapshots, operational catalog records, DB rows or
  embeddings changed; the two new reports remain ignored local artifacts.

### Follow-up — bound cast review evidence to one actor–character credit (7 November 2026)

- Reviewing the retained *The Dark Knight* pilot candidates found that the
  quoted evidence span could continue beyond the actor–character pair through
  another phrase or paragraph. The review UI therefore showed avoidable,
  unrelated cast text even though the candidate character label itself was
  extracted separately. Candidate extractor v8 now stores the exact retained
  substring from the actor name through that character label (for example,
  `Heath Ledger as the Joker`); the article revision and passage hash remain
  attached for wider context. The output/schema and statement extractor are
  versioned v8/v5; older immutable v7/v4 artifacts remain untouched.
- Replayed both retained capture partitions and rebuilt the local-only
  English-100 review report. Totals are unchanged: **100 films, 2,044
  candidates, 1,546 same-film identity candidates, 40 identity-only
  suggestions, 458 unresolved names, 52 quarantined spans, and 1,586
  review-required drafts**. For *The Dark Knight*, 13 same-film drafts remain
  review-required, 3 names remain unresolved and 3 group-role spans are
  quarantined. All five Wikidata character-label matches remain explicitly
  label-only; none is considered a verified actor–character credit.
- The rank 11–100 replay exposed an immutable legacy derivative marker:
  ranks 1–10 use `cinegraph.wikipedia-passage-extraction/v6`, while rank
  11–100 use `/6` with the same exact parser version. The adapter accepts only
  these two observed markers and still requires the exact article revision,
  SHA-256 and parser version; a pure regression covers both. This does not
  alter or rewrite either captured derivative.
- Focused cast policy/coverage tests pass **72/72**; full offline backend
  passes **433 tests**, with **108 PostgreSQL integration tests deselected**;
  Python compilation and `git diff --check` pass. Frontend tests pass **5/5**,
  TypeScript passes, and the Next.js production build succeeds. The explicit
  integration runner was retried against the isolated stack and stopped before
  build or seeding because Docker Desktop could not read the existing API image
  blob (`sha256:2453265d…`, input/output error). Follow-up read-only checks show
  only **2.8 GiB** free on the 460 GiB host volume (reported at 100% capacity),
  and Docker cannot even enumerate its image cache because another content blob
  returns an I/O error. Pulling/rebuilding images or pruning cache in this state
  risks worsening disk pressure and was not attempted. No test database,
  working corpus, containers or volumes were changed. PostgreSQL replay,
  decision persistence and live API behavior therefore remain unverified.
- The new candidate, statement and coverage v9 artifacts are ignored local
  derivatives. No source snapshots, working-catalog rows, rights decisions,
  assertions or embeddings were modified.

### Follow-up — local cache cleanup and integration-stack recheck (7 November 2026)

- Removed only regenerable or unreferenced local artifacts inside the project:
  `frontend/.next-build-check` (98 MiB), `frontend/.next-playwright` (28 MiB),
  and `data/venvs/pair-reranker-site` (329 MiB). The first two had no active
  process using them; `.next-build-check` had no code references, and the
  Playwright output is configured to regenerate. The package-only reranker
  environment had no code/documentation references or running process; current
  experiment instructions use `data/venvs/mlx-reranker`. The active
  `frontend/.next`, required model weights, `rag-encoders`, `mlx-reranker`, raw
  snapshots and evaluation data were retained. Host free space increased from
  2.8 GiB to **3.3 GiB**.
- Retried the isolated test runner after cleanup. It still stops before build,
  migration or seeding because Docker Desktop cannot read the existing
  `cinegraph-integration-api-test` image blob (`sha256:2453265d…`, input/output
  error). Read-only `compose ps` reports the test containers as up, but `exec`
  to `db-test` reports the container is not running; the HTTP health endpoint
  responds from the older API image, which does not contain the new cast-review
  route. This inconsistent daemon state does not prove the current DB/API code.
  The migration graph has one head, `20261107_21`; static compilation and
  `git diff --check` pass. The working corpus and Docker volumes remain
  untouched. Database/API integration is still an explicit unmet gate.

### Follow-up — isolated Docker endpoint recovery attempt (7 November 2026)

- A narrowly scoped restart of only the integration `db-test` and `api-test`
  containers was attempted to resolve the mismatch between `compose ps` and
  `exec`. Docker failed while reading the test DB container's `hosts` file. A
  read-only inspection then showed both containers had empty network endpoint
  IDs despite retaining their expected Compose-network and port-binding
  configuration. `compose up --no-build` and explicit network reattachment both
  failed on further containerd input/output errors. The test API's host port
  `18001` is currently unreachable; its persistent test volumes were not
  removed or reset, and no working-corpus service or volume was targeted.
- This confirms the integration gate needs Docker Desktop/container-store
  recovery before it can be executed; changing application code or deleting
  Docker data from the project would not address the observed host-level I/O
  failures. Keep the database-dependent cast-review changes uncommitted until
  the isolated stack is restored and the current code passes its DB/API tests.

### Follow-up — local pilot snapshot recheck (7 November 2026)

- Added `backend/scripts/recheck_pilot_snapshot_integrity.py` and a pure
  verifier that reads a retained metadata-audit report and checks only the
  exact snapshots previously marked `unmapped`. It records the input report
  hash, film/QID, snapshot ID, URI, expected hash/size and local verification
  result in a new, ignored local report; it never mutates the original audit,
  copies or repairs a snapshot, or fetches a source. A follow-up safety review
  confined file access to the project `data/raw-snapshots` directory; URIs
  outside it are reported as unmapped without being opened.
- Rechecked all 14 previously unmapped snapshot records from
  `catalog-pilot-metadata-audit-v11.json` against their literal local file
  URIs: **8 verified by exact size and SHA-256; 6 remain unmapped** because
  their paths are outside the project snapshot root. A filename-only search of
  the retained project snapshot store found no matching files for those six.
  The versioned report is
  `data/evaluation/catalog-pilot-snapshot-recheck-v2.json` and remains
  local-only. Its result does not change source eligibility, factual review,
  or publication rights.
- Eight tests use real temporary files to verify exact hash/size checking,
  deduplication, conflicting snapshot metadata rejection, input fingerprint
  validation, output-path confinement and rejection of paths outside the
  project snapshot root. No mock framework or database is involved. The
  pre-existing audit remains unchanged; integration work is still blocked on
  Docker's damaged cached image and the `cinegraph_test` API container remains
  unavailable.
