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

1. Version a reproducible pilot list of 100 films: start from the user's chosen
   list, include representative well-known English titles and the requested
   comparison examples where available, and explicitly record additions or
   exceptions. Record language, year and candidate identifiers; do not call
   the CSV a current official ranking.
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

1. Prepare a development set of real writing questions and a separately frozen
   holdout. Include the requested **10 film pairs × 5 questions = 50 holdout
   cases**, with family, loyalty, injustice, character choices, consequences,
   craft and contrast among the question types. Do not tune on holdout results.
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

**Proposed gate, not a current achievement:** on the 50 frozen cases, relevant
supporting evidence is found for *both* films on at least 80% of cases judged
supportable for both films. Report the exact numerator and denominator and all
partially supported/unsupported cases separately. Also report unsupported
claims, misattributions and abstention failures; a retrieval percentage alone
does not qualify an answer as good. Because 50 cases and 10 pairs are small,
show per-pair results and uncertainty and validate on additional unseen films
before claiming general performance.

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

1. Which exact 100-film pilot and which 1,000-film target constitute acceptance?
   The current CSV can seed both, with explicit additions for important test
   pairs; the target list should be versioned.
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
