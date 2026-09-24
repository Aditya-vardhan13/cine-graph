# CineGraph audit: 14 September 2026

Audited revision: `3d033c1`. This is an assessment, not an implementation or deployment approval.

## Verdict

CineGraph has a credible local research foundation and an early evidence-comparison interface. It is not yet a validated screenwriting product or a production-ready service. Keep PostgreSQL/pgvector, FastAPI, Next.js, retained source snapshots, and local model serving. Change the sequencing: make existing evidence consistently available and demonstrate useful comparisons before expanding collection volume or infrastructure.

The architecture is directionally appropriate, but describing it as future-proof would be inaccurate. Some new paths follow the documented boundaries; legacy API paths and catalog projections still bypass them. Targeted maintenance is necessary. A commitment to never refactor cannot be guaranteed by SOLID or any design pattern.

## Audit method and limits

Inspected architecture documents, current source, migrations, test contracts, stored evaluation reports, the live local API, and read-only PostgreSQL queries. Verified the home page contains the comparison workbench and exercised a comparison through the frontend proxy. Twelve focused policy tests passed in 0.95 seconds.

The complete integration suite and model benchmark were not rerun. Stored benchmark measurements are historical. No visual browser, mobile, keyboard-accessibility, concurrency, restore, or production deployment test was performed. Findings about visible layout derive from components, styles, and returned HTML, not a screenshot inspection. No independent human evaluation is claimed.

## Measured data inventory

| Measure | Observed result | Interpretation |
| --- | ---: | --- |
| Retained research collection | 1,000 films | Enough to test the initial product |
| Retained narrative passages | 24,446 | All belong to English Wikipedia |
| Research films with passages | 1,000 | Presence, not complete coverage or correctness |
| Active embedded chunks | 24,194 across 1,000 films | Full selected-index coverage |
| Eligible chunks across retained preprocessing runs | 72,824 | Three versions; do not count as independent material |
| Research films with legacy Film profiles | 128 | Only 12.8% share the older display projection |
| Resolved operational assertions in collection | 80,456 across 1,000 films | Policy-resolved, not independently human-verified |
| Assertions requiring review | 1,002 across 588 films | Unresolved records remain |
| Critical works | 8 | All metadata/link-only and review-required |
| Extracted critical claims | 0 | Essay interpretation layer is not populated |
| Scholarly discovery candidates | 5,057 | 4,504 Crossref and 553 OpenAlex; all pending |
| PostgreSQL database size | 858 MB | Excludes external snapshots and model artifacts |

The original local CSV contains 1,001 rows, with parseable years from 1920 through 2020. Of these, 486 are from 2000–2025; none are from 2021–2025. This describes the seed file, not a complete live-corpus year audit. It cannot establish the requested coverage through 2025. An English Wikipedia page also does not establish that the film's original language is English.

Section coverage provides a better depth measure than total rows: 989 films have a top-level plot section, 916 production, and 811 reception. Counting section paths containing reception or legacy yields 970 films; paths containing themes yield 208. Alternate headings may account for some apparent gaps, so these are extraction-coverage indicators, not proofs that the films lack the information.

Wikipedia is substantial enough for the first comparison product. It is not evidence of diverse independent interpretation across all 1,000 titles. Pending academic metadata is not ingested essay text. The CMU corpus is additional retained material, but it is not equivalent to indexed, reconciled coverage for the research collection.

## Priority findings

### High: lexical retrieval mixes preprocessing versions

`backend/app/services/hybrid_evidence_retrieval.py:126` filters lexical candidates by film and eligibility, but not preprocessing run. Semantic candidates use one index run. The database retains three eligible preprocessing runs, and 24,194 subject/content-hash groups occur more than once.

Consequently, hybrid rankings can combine different versions and repeated evidence. `_first_unique` in `story_comparison.py:161` deduplicates only chunk IDs and explicitly returns a repeated candidate when no unused candidate remains. It does not prevent equivalent text appearing across different chunk IDs.

Required outcome: bind every request to one immutable retrieval configuration, use its preprocessing run in both rankers, and test content overlap across lenses. Retaining old versions is correct; querying all of them accidentally is not.

### High: the improved data is only partially exposed to users

All 1,000 films now have resolved assertions, but only 128 have legacy Film profiles. `research_catalog.py:39` still derives date, runtime, and genre from the optional legacy profile. The live Her search returned a title with null date/runtime and empty genres despite the newer assertion layer.

Required outcome: one canonical catalog read contract backed by explicit display-value policies for current assertions. Dates, currencies, release territories, and competing source values require deliberate resolution. Do not simply take the first assertion. Existing legacy screens can consume an adapter to that contract.

### High: the quality dashboard undercounts the new corpus

`api.py:194` counts `NarrativeDocument` through `CorpusRecord`, not the newer `NarrativePassage` pipeline. The live endpoint reports zero Wikipedia narrative documents while the database holds 24,446 Wikipedia passages. The home page presents this as its corpus quality board.

Required outcome: count canonical collection coverage, passage coverage, active-index coverage, and review states explicitly. Source registration, bibliographic discovery, retained text, and reviewed interpretation must have separate counts. The user-facing home page should emphasize research usefulness; detailed operational accounting can remain a local report.

### High: comparison relevance has not passed a product evaluation

The live Her / Blade Runner 2049 question about artificial companionship completed through the web proxy in 1.70 seconds with hybrid retrieval. Some passages were useful, but Blade Runner 2049's central-question result described the reproduction investigation; the reception result concerned K's fate and Deckard's identity. Neither directly explains the reception of AI intimacy.

The current service supplies five fixed lenses and selects ranked passages without a calibrated relevance/abstention policy. It provides no generated comparison, evidence-based recommendation of another film, or saved writer research workflow. Populated cards should not be equated with answered questions.

Required outcome: evaluate all displayed passages for relevance, sufficiency, overlap, and unsupported premises. Retrieve wider context when necessary; allow a lens to say that available evidence does not answer the question. Do not infer this decision from a universal cosine threshold.

### Medium: benchmark success is narrower than the intended product

The stored 150-case held-out report records system MRR@10 0.8447, narrative hybrid MRR@10 0.8059, cross-film MRR@10 0.7256, and target recall@10 1.0. These are useful results for film-scoped, intent-routed retrieval. Gold labels explicitly remain assistant-reviewed and human-review-required.

The benchmark does not establish open-catalog discovery, independently judged usefulness, or performance on unanswerable questions. Its cross-film tests retrieve separately for two known films. Its original objective-fact test covered the smaller pre-projection intersection. The current UI displays one passage per film/lens, so recall at ten is insufficient to validate that display.

Required outcome: preserve this regression suite, add independent writer-task review and fresh untuned queries, measure precision at the displayed cutoff, and report abstention and first-use latency separately.

### Medium: maintainability and scale boundaries are uneven

- `api.py:423` loads all published candidate films with genres and credits and scores them in Python. A per-request full-catalog scan cannot be the million-film recommendation path.
- Lexical ranking computes text vectors at query time; the new canonical search does not use the existing legacy-title trigram index. Query plans need measurement as collection size grows.
- Active index selection picks the latest completed run by model name. Future collections require explicit collection/run compatibility; model dimensions are currently constrained to 1,024.
- New services separate pure policy from orchestration reasonably well. Several older HTTP handlers still contain SQL and scoring logic. Consolidate hot-path responsibilities incrementally; avoid generic repositories for every table.
- English tokenization, PostgreSQL English text search, fixed section rules, and fallback language labels remain. Language-neutral identities are useful preparation, not completed multilingual retrieval.

## UI assessment

Implemented: dark styles, live title selection, film/person detail pages, lineage, and a two-film evidence board with links to sources. The running home page contains the new workbench, but has no nav element. It still leads with lineage messaging and a lengthy quality board before the comparison workbench.

Missing for a coherent initial writer product: consistent catalog coverage, focused research navigation, question-to-film discovery, clear comparison conclusions, and saving/exporting a useful research session. A full screenplay editor can wait until research usefulness is demonstrated.

There is also a response race risk: users can edit the question or film selection while comparison fetch is pending; the eventual response is accepted without checking that it belongs to the current inputs. Search lacks a dedicated no-results presentation in the new workbench. Browser interaction tests should cover these cases, navigation, keyboard selection, and mobile layout.

## Deployment and scale

The local stack is deployable in principle, but the current compose file is development configuration: default database credentials, exposed database/API ports, a host-bound Ollama URL, and migrations executed at API startup. I found no committed CI workflows, deployment runbook, or tested backup/restore procedure. The API's embedding adapter allows a 120-second timeout, which is not a suitable interactive latency target.

Before a private deployed beta: establish secrets and network boundaries, a single migration job, model readiness and warm-up policy, bounded request/queue time, access control appropriate to the beta, structured errors/metrics, automatic tests, and a database-plus-snapshot restore drill. Ingestion and embedding builds should remain separate from serving. Data remains local until deployment is explicitly authorized.

Keep one application/backend and PostgreSQL/pgvector initially. A separate graph database, multiple cloud providers, or distributed services have no demonstrated benefit for the current workload. Hosting selection should follow measured concurrency, model memory/throughput, and restore requirements; no honest cheapest-provider conclusion follows from the present evidence.

For an order-of-magnitude scale model, retaining today's 24.194 indexed chunks per film gives approximately 24.2 million vectors at one million films. At 1,024 float32 components, vector payload alone is about 99.1 GB decimal, excluding row overhead, text, HNSW, snapshots, replicas, backups, and retained versions. At the historical 4.74 chunks/second local build rate, that initial embedding build would take about 59 days continuously. These are linear extrapolations, not forecasts.

One million films also imply roughly 500 billion unordered pairs. Discovery must shortlist candidates and inspect evidence on demand rather than precompute every pair. Known-film retrieval and open-catalog discovery need separate evaluation and query plans. pgvector documents that approximate-index filtering can affect recall; an HNSW index alone is not proof that filtered queries will scale correctly: https://github.com/pgvector/pgvector#filtering

Ollama's documentation also describes model loading and concurrency/memory tradeoffs; deployment latency needs both cold and warm measurements: https://docs.ollama.com/faq

## Recommended sequence and acceptance gates

1. **Repair current correctness and visibility.** Pin retrieval runs; address overlapping evidence and request races; expose current assertion-backed metadata; correct quality counts. Gate: retained versions cannot contaminate current results, and catalog/search/detail agree about film identity and coverage.
2. **Audit depth across the existing 1,000.** Produce per-film coverage for identity/year/language, plot, craft, reception, themes, and provenance. Inspect the 11 apparent plot gaps and alternative headings. Review a stratified 100-film sample across date, genre, and depth. Gate: missing information and identity uncertainty are enumerated; automated resolution is never reported as human vetting.
3. **Validate the product with 20 film-pair tasks.** Include AI intimacy, return to power, institutional corruption, survival/extinction, craft, and reception. Add negative/unanswerable questions. Independently review the actual displayed output. The existing 70% useful-task gate can be an initial threshold, but document the rubric and failures. Do not tune and rebrand the same set as a fresh held-out test.
4. **Fill demonstrated source gaps.** Prioritize missing 2021–2025 titles and specific unanswered questions. Admit relevant criticism with attribution and appropriate reuse scope. No fixed article quota per movie is justified; enough evidence to support or challenge the question is the criterion.
5. **Complete the writer workflow.** Add catalog-wide candidate discovery, then cited comparisons and saved/exportable research after their evidence quality passes review. Keep interpretations attributed and direct relationships separate.
6. **Prepare a private beta and measure load.** Exercise the real user journey at increasing concurrency, choose explicit latency/error targets, and perform recovery tests. Expand toward 10,000 and 100,000 records only with storage/build/query measurements. One million is a capacity scenario, not the next milestone.

## Honest assessment of time spent

The retained evidence, identity model, versioned chunks, resumable embeddings, and isolated database tests are valuable foundations. However, corpus acquisition, model experiments, and architecture documents have advanced faster than the end-user validation loop. The time spent cannot be justified solely by counts or benchmark improvements. The next milestone should demonstrate that a writer gets a useful, trustworthy comparison from the existing data.

The first-principles assessment changed the priority, not the stack: volume is not usefulness; provenance is not correctness; successful deployment is not proven capacity. Enough data exists to test the initial product now. Broad critical interpretation and recent-film coverage remain unfinished.

## Addendum: raw snapshot integrity check (23 September 2026)

A read-only audit of the local working database found a more urgent evidence-retention gap than the original report captured. All 1,000 snapshots from the original English Wikipedia acquisition and 905 original Wikidata snapshots have `storage_uri` values under `file:///private/tmp/cinegraph-pilot-raw/`; that directory no longer exists. The retained narrative passages, operational assertions, and vectors still support current reads, but their original captured payloads cannot presently be replayed from those paths. This does **not** establish that the derived data is false; it does mean the immutable-source portion of the evidence chain is incomplete for those records.

The separate `aarambham_raw_snapshots` Docker volume contains 312 files. Of these, 310 match recorded snapshot hashes and all 310 pass SHA-256 verification. They are not replacements for the missing original acquisition: none of the 1,905 records pointing to the temporary path resolve to files in that volume. Later acquisition accounts for 186 additional English Wikipedia snapshots and 124 additional Wikidata snapshots under `/var/lib/cinegraph/raw-snapshots`; the volume also contains two files not referenced by current snapshot records. A targeted search of the workspace data directory did not locate sample missing hashes. Other local backups have not been ruled out.

The new read-only checksum audit (`python -m app.services.snapshot_integrity`, run with the raw Docker volume mounted) confirmed 1,000 missing and 186 verified English Wikipedia snapshot records. For Wikidata it found 906 missing and 124 verified records; the extra missing record points to a different, container-local `/app` path. The command checks only files visible in its own filesystem namespace, so mount the relevant local snapshot roots before interpreting a source-wide result.

Before calling the 1,000-film corpus reproducible or expanding ingestion, either recover the exact original bytes from a backup, or run an explicitly rate-limited, policy-compliant reacquisition of the pinned source revisions. Any changed payload must become a **new** snapshot with its own hash and downstream versioned extraction; never rewrite an old `SourceSnapshot` URI or imply that a newly fetched revision is the original capture. Keep persistent raw storage outside temporary directories, back it up with PostgreSQL, and perform a restore drill. Do not commit raw payloads or the local database to Git.

A manual, sequential pinned-revision recovery is now in progress. The new `wikipedia_revision_recovery` adapter stores the exact API response as a new snapshot and stops on denial/rate-limiting; it does not rewrite the old row. A read-only `wikipedia_recovery_audit` recomputes section locator, ordinal and content hash from the newly captured wikitext. At an intermediate check, 179 recovered films reproduced all their old passage keys (3,910 of 3,910), with zero mismatches; 821 films had not yet been recovered. This intermediate result is **not** a completed 1,000-film gate. After capture, run the audit across all 1,000, create new versioned passage records linked to the new snapshots, then rebuild or safely reuse exact-text vectors in a new index run. Do not silently switch old chunks to new provenance.

The user-facing sequencing and writer-task acceptance test are specified in [writer-research-product-gate-v1.md](writer-research-product-gate-v1.md). It is a design and evaluation gate, not evidence that the current UI has passed it.

### Recovery checkpoint (23 September 2026, later in the run)

The first long recovery batch stopped after 475/989 captures because the remote server disconnected without sending a response; it recorded no denied or rate-limited record. Together with 11 earlier pilot captures, 486 new snapshots had been stored and verified. The adapter now retries transient transport and 5xx failures with bounded backoff; denial still stops immediately, and a resumed run skips verified captures. Its new batch began with 514 remaining targets.

A subsequent read-only equivalence pass found 508 recovered old revisions, all 508 reproducing their old passage locator/ordinal/hash sets (12,231 matching passage keys), with zero mismatches. The remaining 492 were still unavailable at that moment. This is an intermediate audit, not final corpus vetting. Only one film's recovered passages had been re-materialized at this checkpoint (15 passages), so source capture must not be conflated with retrieval readiness. The version-scoped coverage report and preprocessing guard now make that distinction explicit.

An expanded integrity audit also checked Crossref and OpenAlex, whose storage URIs use the workspace's `data/raw-snapshots` root. They initially appeared missing inside a container that mounted only the Docker snapshot volume; with **both** roots mounted, all 4,467 Crossref and 544 OpenAlex snapshots passed checksum verification. Do not count a path as lost merely because the audit process cannot see its host mount. The same correctly mounted audit still found 1,000 missing original English Wikipedia descriptors and 906 missing original Wikidata descriptors. At that checkpoint, explicit `AssertionEvidence → SourceAssertion → SourceSnapshot` links exposed 67,947 resolved and 866 review-required assertions dependent on unavailable Wikidata snapshot bytes. This impact count covers explicit links only, not every legacy fact that may cite Wikidata by URL or revision.

### Recovery and preprocessing completion checkpoint (24 September 2026)

The resumed Wikipedia recovery completed its remaining 514 targets with zero failures. The final equivalence audit is exact for all 1,000 films: 24,446/24,446 old passage keys match, with no mismatch or unavailable revision. The versioned passage materializer created 24,431 new passages (15 already existed), and the read-only coverage report now accounts for all 1,000 films and 24,446 passages. Its section-heading inventory reports plot 999, production 940, reception 998, writing/craft 534, themes/analysis 261, and legacy 356; these are prioritization signals, not judgments that the remaining films lack those ideas.

The new source-scoped preprocessing run `0892ebfc-8b33-4051-95da-4a239b288e40` completed over all 24,446 passages: 25,959 chunks, 24,194 eligible, 1,761 excluded for explicit quality flags, and 4 exact duplicate chunks. Every film has at least four eligible chunks.

The exact-input audit showed that all 24,194 eligible chunks match the documents in the prior complete Qwen3 Embedding 0.6B index one-to-one (film, language, section, text, and content hash); the prior index's cache key also still verifies. Rather than spend another local model pass on identical text, the guarded reuse service created a new completed index run, `0adc1904-7788-4f65-8622-1e449b1f612e`, for the recovered-source chunk run. It contains 24,194 vectors. This is a versioned database-side reuse of exact vectors, not a new embedding-model evaluation or a retrieval-quality improvement claim. The isolated PostgreSQL integration suite passes (46 passed, 66 deselected), including multi-row copy and mismatch rejection.

At this checkpoint, Docker-container-to-Ollama reachability was still unverified, and the first persisted retrieval evaluation had no matching passage IDs. Both findings are resolved or clarified in the retrieval subsection below. Wikidata's 906 unavailable original snapshots and their explicitly linked assertion impact remain unresolved and must not be silently folded into this narrative index.

### Retrieval smoke and evaluation-label recovery (24 September 2026)

The empty first retrieval-validation report was caused by evaluation answers pointing to passage UUIDs from the earlier source materialization. The recovered passages have new UUIDs, even though their exact source URL, source revision, section locator, ordinal, and content hash match. The evaluator now maps labels between materializations only when all of those fields match; it does not rewrite reviewed answer/evidence records. A real PostgreSQL integration test covers this exact-version mapping. The full isolated suite passes: 47 passed, 66 deselected.

With the label mapping, the existing narrative seed contains 11 evaluable `narrative_extraction` questions. All 11 retrieved a linked passage at rank 1 (Recall@10 1.0, MRR@10 1.0). Warm/local query-embedding latency was p50 89.7 ms and p95 490.2 ms; database-ranking latency was p50 8.6 ms and p95 22.4 ms. This is encouraging smoke coverage only: the sample is small, labels are passage-level, and it is not a held-out benchmark. Do not generalize these scores to all 1,000 films or claim broad retrieval quality from them.

A real host-native API request comparing The Dark Knight and The Matrix returned HTTP 200 with hybrid retrieval, no semantic fallback, and evidence on both sides of all five lenses in 729 ms. The API process was bound only to localhost and stopped after the check. The Dockerized API still cannot connect to Ollama because the host daemon listens only on `127.0.0.1:11434`; keep it that way rather than exposing the model service broadly. For local development, run PostgreSQL in Docker and the API and frontend natively on localhost. A future all-container setup should run Ollama on the private Compose network.
