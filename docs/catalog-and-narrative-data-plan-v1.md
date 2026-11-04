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

1. Add/run browser assertions for release precision, alternate territory
   events and missing/conflicted runtime states; API/PostgreSQL integration
   already passes in the isolated `cinegraph_test` stack. Keep browser checks
   pointed at the isolated stack and never mutate the working corpus.
2. Resolve the 17 runtime-ambiguous films and one date exception by inspecting
   source assertions and version/territory qualifiers. If evidence does not
   establish one display value, keep the field explicitly unresolved.
3. Add source-specific intake adapters only after recording terms, license,
   rate/access policy, attribution and fields supplied. Dataset admission is
   field-level: useful structured metadata may enter its own provenance lane,
   but does not grant rights to unrelated plot/review text bundled with it.
4. Exercise one full title-to-evidence vertical slice on a small stratified
   batch: disambiguate identity; snapshot authorized sources; extract typed
   assertions and sectioned passages; validate identity, rights, checksum and
   coverage; review; index eligible passages; retrieve cited evidence. Keep
   every stage resumable and idempotent, and publish gaps rather than silently
   filling them.
5. Only then enrich the 100-film pilot, compare per-film coverage against the
   frozen baseline, and expand to 1,000 in checkpointed batches. Do not claim
   a 1,000-film-ready corpus from the size of a source dataset alone.

The broader catalog remains additive and language-neutral. Each incoming
dataset must pass identity-link, field-definition, license/attribution,
provenance, duplicate, conflict, coverage and sample-quality checks before it
is eligible for batch ingestion; raw payloads, snapshots and derived vectors
remain local and out of Git.
