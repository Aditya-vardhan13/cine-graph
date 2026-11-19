# CineGraph: 24-hour product recovery plan

## Decision

Build a film research desk that gives a writer a **specific comparison they
can verify and use**. A good answer shows what each film does, where the
comparison breaks down, and one craft decision the writer can apply to a
different story. A pile of relevant-looking excerpts is not an answer.

Replace 0.6B in serving with a verified **4B-or-larger** embedding model.
Do not spend another tuning cycle on 0.6B. Preserve the old run's provenance
and metrics; do not tear down the current rollback assets before proving the
replacement. Plan for Qwen 4B, Qwen 8B, and an optional third arm; generation
is a separate 4B/8B choice. No new vector database, fine-tuning, or recommender
rewrite in this sprint.

This is a **24-hour, elapsed-time sprint to a measured go/no-go**. It is not a
promise to manually certify 1,000 films, achieve 80%, or launch publicly in
24 hours. If a gate fails, deliver the finished artifacts, demonstrated
failure and remaining critical path. Never move the threshold mid-run.

## What winning looks like

Study begins with films and a question. The first result is a concise answer,
separate observations for each film, the strongest contrast, and a writer's
move. Claims link to revision-specific evidence with expandable surrounding
context. Explicitly flag spoilers, disagreements, missing coverage, and
interpretation. If only one film supports a premise, give a one-sided answer
with the gap stated. If neither does, explain what source would be needed.

Example: asking about artificial companionship in *Her* and *WALL-E* should
surface the difference between a human/OS relationship and a robot-centered
story, explain the distinct dramatic mechanisms, and let a writer compare
techniques without inventing symmetry. If the answer could be supplied
without reading any film evidence, ask whether the product added value.

**Competitive test:** compare blind with general-chat answers to the same
question, first without supplied evidence, then with the same cleared
evidence packet where sharing is allowed. The first tests user value as
experienced; the second tests whether CineGraph adds anything beyond its
evidence access. Record exact comparator/date/settings. If unavailable,
report that comparison as unrun. Never upload local-only or restricted text.
Do not claim superiority from model scores alone.

## Evidence and first-principles constraints

- [Audit](corpus-audit-2026-11-18.md): 1,000 collection films, 24,479 current
  passages, predominantly Wikipedia. Only two films had eligible indexed
  evidence under the audited live policy. 966 current vs indexed article
  object/revision pairs did not match. The supplied CSV and collection are
  separate denominators with unresolved identities.
- The ceiling on fully grounded answers is the fraction of questions for
  which admissible evidence actually supports all required facets. Larger
  models cannot raise that ceiling; they can improve selection and synthesis.
- Existing 4B reranking experiments had high local cost and narrow evidence;
  old whole-story leaderboards do not measure question-specific evidence
  retrieval. Treat poor retrieval, missing evidence, and bad synthesis as
  three different problems.
- Serving currently selects 0.6B by default; persistence enforces
  `Vector(1024)`. Dimensions, model revision, normalization and query
  instruction must match at build and serve time. No mixing vectors.
- Minimum raw vector bytes = chunks × dimensions × 4 for float32. At the
  audited 24,194 indexed chunks, 1,024/2,560/4,096 dimensions use about
  95/236/378 MiB before tuples, search indexes, WAL, checkpoints or caches.
  At 100× scale it is about 9.2/23.1/36.9 GiB of vectors alone at the same
  chunk density. These are math, not observed disk estimates.
- Source capture, identity, rights, extraction, indexing and activation are
  different states. Publication alone does not make a film retrievable.
  No paid scope can inherit the local non-commercial IMDb/TMDb setting.

## Workspace disposition and cleanup

Inventory pass, 19 November: ~28 GiB in the project, ~78,101 regular files
before cleanup, 532 tracked or unignored paths at the pass, including dirty
work. This was a filesystem inventory and targeted dependency/size review,
not a semantic read of all 78,101 files. `df` showed ~9.3 GiB free before
cleanup and ~9.4 GiB immediately after; APFS free space can fluctuate. Scope
is this repository only. No changes to Docker volumes, global caches or
files outside the repository.

| Asset | Disposition | Why / implementation |
| --- | --- | --- |
| IMDb `title.episode.tsv` | **Removed**: 260,911,201 bytes (~249 MiB). | Film-only importer enumerates six inputs and does not use episode rows. Ignored, untracked, regular file, no open handle observed. Not recoverable from Git or Trash; re-acquire from IMDb if TV becomes a requirement. |
| Other IMDb TSVs (~8.6 GiB after removal), root names TSV (~0.9 GiB), IMDb lookup index (~154 MiB) | Keep temporarily; derive a bounded film-only extract if shrinking is necessary. | All six inputs are consumed by local ingestion. A small extract must prove exact-ID, aliases, crew and actor/character parity and missing-row behavior; preserve hashes and terms. Do not remove the original dumps if current intake or future catalog expansion still depends on them. |
| Supplied 1,000-row CSV and ID manifests | Keep and reconcile. | Canonical target reference for this sprint, not evidence of a current ranking. |
| Raw snapshots, source refresh and intake captures | Keep and transform. | Unique evidence, alternate revisions, replay materials. Verify paths/hashes; derive rather than overwrite. |
| CMU archive and extracted Wikipedia/Freebase data | Keep as historical discovery; do not copy into serving. | 42,306 plots, 81,741 metadata lines. 798 current films overlap on exact page IDs with a historical plot candidate. Compare versions selectively; preserve dataset release and terms. |
| SemEval/MF² releases, annotations, retained comparisons | Keep evaluation-only. | Distinguish benchmark from corpus, validate split overlap, quarantine malformed/identical fact–fib records. Gold never feeds retrieval. |
| Evaluation model cache (~2.2 GiB BGE-M3) | Conditional retirement candidate, not deleted. | Below new embedding requirement but still has reproducibility consumers. Preserve revision and reports; verify no active jobs or required replay, then remove only documented disposable weights if retired. |
| Local Ollama store (~7.8 GiB); MLX model directory (~4.3 GiB) | Keep named 4B/8B generation and 4B reranker pending trials; retire 0.6B runtime once cutover is verified. | Ollama blobs can be shared by tags; remove through the model manager against the proven correct store only. Separate legacy experiment references from runtime dependencies. |
| Legacy root SQLite (~24 MiB) | Retain pending source/backup check. | Alembic still references the path; confirm no unique data before deleting, regardless of current Postgres use. |
| Working copies, fixtures, logs, backup manifests and credentials | Keep; never expose secrets. | Dirty user work and audit history are not redundant. No copy of inputs to Git. |

Before additional cleanup enumerate ignored, tracked, untracked, and symlinked
paths and measure physical space. For each removal record owner/consumer,
running-process check, references, exact target, bytes, and recovery. For raw
duplicates prove hashes and confirm no snapshot URI or replay refers to the
copy. For model caches confirm exact digest, dependencies and lifecycle; a
smaller footprint is not enough reason to remove a useful asset. No broad
`git clean`, prune, or recursive delete of source trees/data roots. No
`node_modules` or current build deletion merely because they are rebuildable.

### Transform useful, underused data

| Input | Derivative | Prove value before promotion |
| --- | --- | --- |
| Verified film pages plus current assertions | A film dossier keyed by entity/edition, with roles, release-event alternatives, typed sections and citations. | Compare exact field values in API/UI against retained source records; don't use credits as narrative evidence unless the question calls for credits. |
| Pending Crossref/OpenAlex leads | Deduplicated DOI/URL queue grouped by film, relevance, article rights, and whether it adds a perspective beyond Wikipedia. | Manually inspect pilot-film results; count usable independent arguments, not links or journal hits. Link-only remains separate from eligible full text. |
| CMU page-ID matches | Historical-version diagnostic and candidate discovery input. | Compare only matching source objects; look for a missing action or contrast rather than including both versions by default. Do not treat a different wording of Wikipedia as independent corroboration. |
| Public discussion prompts and known bad CineGraph outputs | Versioned question packet and regression cases. | Preserve prompt provenance and dated search observations; create independent support labels from admitted film evidence, not from online answer keys or model text. |
| SemEval and MF² | Offline story-similarity and finer-grained claim checks. | Keep official labels out of prompts, track split/work overlap, and flag video-dependent cases. These checks do not count toward the writer quality gate. |
| Old chunks/vectors | Use report-level comparison and possible rollback only. | Never reuse a vector under a new source, embedding template, dimensions, or digest. Identify unused superseded matrices only after checking replay consumers. |

## Corpus build: make 1,000 a reconciled target, not a marketing count

1. Freeze target CSV bytes and exact rank/source labels. Output one row for
   every CSV row: stable target row key, canonical entity ID or explicit
   unresolved reason, validated external IDs, release/edition distinction,
   source snapshots, current approval and retrievable status. Report duplicates
   and coverage separately. Review title/year/director conflicts; do not force
   joins. Start with audited identity exceptions and remake collisions.
2. Build a source inventory with purpose-level admission: typed metadata,
   local non-commercial display, semantic indexing, generation input, and
   evidence display. Keep identity, rights and content checks separate.
   Fix host-to-container resolution with an explicit allowlisted root map,
   traversal and symlink containment, and exact hash verification. Test
   retained good and bad paths. Do not mutate immutable URIs or bulk approve
   snapshots. Resolve publisher/asset terms when uncertain.
3. Take already-retained English Wikipedia material first, irrespective of
   original film language; use the local metadata projection for cast/roles,
   genres and identity. Correct source-specific dates/runtimes without
   inventing a release day or dropping conflicts. Don't infer original
   language from the article edition. Record a separate coverage report for
   English, Telugu, Hindi, Tamil and other languages using sourced fields.
4. Derive section-typed evidence: plot/character action, production/craft,
   criticism/reception, cultural/industry legacy, and unresolved/other.
   Keep raw and display text separate. Strip malformed wiki artifacts only
   with reproducible parser rules, preserving source spans, hashes, section
   title and revision. Keep sequences and attribution with their context.
   Validate old/new section coverage and quarantine artifacts and title drift.
5. Derive embedding text using a shared template: film identity and edition,
   section path, contextual neighboring sentences where needed, and passage.
   Keep context and verbatim evidence distinct. Start with paragraph-aligned
   windows around 350–550 tokens and check fragmentation; this is a tested
   starting range, not a universal optimum. Keep source passage and parent
   offsets so a retrieved fragment can expand to the whole relevant action.
   Count with each actual tokenizer; never silently truncate. Inspect film
   names/aliases and negations; prevent title text from swamping the query.
6. Deduplicate within film/source via normalized hashes and near-duplicate
   clustering; retain alternate sources and meaningful disagreement. Do not
   merge films or treatments based on textual similarity. Track per-film
   coverage by evidence type and unresolved/rights state. Emit immutable
   chunk runs, file hashes and a manifest of what was included/excluded.
7. Fill measured gaps: find critical perspectives in publisher and journal
   sources, primary interviews for production decisions, and official
   award/industry records where needed. For each candidate verify scope,
   article licence, film identity and evidence usefulness before ingestion.
   Use link-only attribution when full-text use isn't established. Follow
   published terms/robots/rate limits; stop on block/rate-limit responses.
   Never turn modern reviews, scripts or commentary into an assumed corpus
   just because they are accessible. No mass crawl in the sprint.

Release statuses: `identified`, `captured`, `verified`, `reviewed`,
`indexed`, `serving`. Expose distinct coverage and eligibility states in
the catalog, and index only the immutable manifest reviewed for that scope.
Use a separate writer/pilot collection; never mutate the frozen test set.

## Embedding experiment and cutover

Primary research: [Qwen 4B model card](https://huggingface.co/Qwen/Qwen3-Embedding-4B),
[Qwen 8B model card](https://huggingface.co/Qwen/Qwen3-Embedding-8B-GGUF),
[MTEB leaderboard](https://huggingface.co/spaces/mteb/leaderboard),
[Ollama published tags](https://ollama.com/library/qwen3-embedding/tags),
[BAAI's 7B candidate card](https://huggingface.co/BAAI/bge-en-icl).
Use published retrieval results and loading details to shortlist, not the
overall ranking to choose. Model-card scores are not claims about the
quantized artifacts, the 1,024 dimension setting, or CineGraph questions.

| Arm | Run | What it isolates |
| --- | --- | --- |
| A | Qwen3-Embedding 4B Q4_K_M, published ~2.5 GB | Minimum acceptable serving candidate. |
| B | Qwen3-Embedding 8B Q4_K_M, published ~4.7 GB | Capacity comparison with the same family and quantization tier. |
| C | Qwen3-Embedding 4B Q8_0 (~4.3 GB), **or** BGE-en-ICL 7B if an exact, licensed local artifact fits | Q8 tests quantization sensitivity; BGE tests family independence. Record which actually ran; never call Q4/Q8 two model families. |
| Control | PostgreSQL lexical, no 0.6B model run | Verify dense adds something over exact terms/aliases. |

Smoke-test exact tags and digests, model license, tokenizer and 1,024-dim
output, finite nonzero norms, matching query/document configuration, and
behavior on long input. Qwen supports reduced output dimension, but verify
the exact local adapter/artifact. Mismatched profile fails closed. First
compare common 1,024-dimensional vectors with identical frozen chunks,
lexical lane, queries and fusion. Run a native-dimension offline sensitivity
check only if common-dimension quality is the bottleneck and resources permit.
[pgvector](https://github.com/pgvector/pgvector) documents dimension limits
for indexed types; don't assume a native 4B/8B vector can use the same index.
For two selected films use exact scoped cosine when measured fast enough.
Avoid an approximate search index and schema change until target workloads
show a need; keep Postgres as the source of truth.

Operational plan: make serving choose a pinned model + index run for the
active collection, never a hardcoded default or “latest finished run.” Store
adapter, tag, full digest, dimension, document/query headers, storage dtype,
normalization and corpus hash. Build an inactive index, verify expected row
counts, completeness, hashes, revocations and query behavior, then activate
explicitly. Evaluate rollback in isolated Postgres. If the new run fails, do
not activate it or purge working assets; show unavailable/lexical only if
explicitly configured and validated. On success retire the old *runtime*
dependency, preserving audit artifacts. Do not download or purge models in
this planning turn.

## Real questions and acceptance

Pick these ten diagnostic films provisionally, verifying identities and
availability: *Endgame*, *The Godfather*, *Her*, *WALL-E*, *Jaws*,
*Jurassic Park*, *12 Angry Men*, *The Shawshank Redemption*, *3 Idiots*, *PK*.
Use ten pairs (five natural pairings and five justified cross-pairings),
five questions per pair. Include relationship/choice, consequence,
craft, reception, and a difficult asymmetric or false-premise question.
Search for actual recurring public question themes, using paraphrases
and source URLs/dates in an evaluation manifest. Recurrence across two
independent venues is a demand signal, not a surveyed popularity estimate.

Starter prompts, **development only**:

- How does the audience infer loneliness in *Her* and *WALL-E* before the
  story states it? What changes when one film relies on visual exposition?
  [Pixar production notes](https://www.pixar.com/wall-e) are a question
  discovery and verification lead, not automatically licensed RAG text.
- How do *Jaws* and *Jurassic Park* turn financial pressure into suspense?
  Compare institutional choices separately from production techniques.
  [AFI's Jaws entry](https://catalog.afi.com/Film/55193-JAWS) and the
  [National Film Registry](https://www.loc.gov/programs/national-film-preservation-board/film-registry/descriptions-and-essays/)
  supply craft and discussion leads, not causal claims that carry across films.
- Where do *Endgame* and *The Godfather* distinguish protecting one's family
  from protecting one's group? [Academy archive](https://www.oscars.org/collection-highlights/godfather?fid=57036)
  is a development lead; retain the user's phrasing as a known regression,
  never a blind example.
- Does the verdict in *12 Angry Men* establish innocence? How does that
  differ from what *Shawshank* tells us? [Teach with Movies discussion guide](https://teachwithmovies.org/12-angry-men/)
  identifies the debate; its wording is not answer gold.
- Which people bear the cost of challenging authority in *3 Idiots* and
  *PK*? Use the [audit's source probe](corpus-audit-2026-11-18.md) as a
  development regression; source public recurrence before claiming popularity.

Reserve 20 sealed questions on four pairs for one-time release assessment;
30 are development diagnostics. Keep pair-disjoint questions and minimize
film reuse between sets; if a film recurs, publish overlap and never call the
test film-disjoint. Prefer a later 50-case, different-film holdout before
public launch. The known questions above are not valid hidden examples.
Seal before ranking: exact editions, answerability, per-film required facets,
positive source spans plus equivalent alternatives, expected abstentions,
hard negatives, and matching citation rules. Review from full source context
before looking at ranks. Second reviewer adjudicates ambiguous cases; if
not available, label the score single-reviewer and make no release claim.

Score in sequence:

1. **Source oracle:** can admitted text answer the required facets? Label
   complete, partial or missing with reason, regardless of retrieval rank.
2. **Candidate recall:** were support spans available in top 20 per film?
   Report both per-facet and per-pair coverage against oracle-answerable cases.
3. **Displayed evidence:** are both films' required facets represented in
   top five per film without duplicate fragments dominating? Keep query
   classes and failure examples, not only MRR.
4. **Generation on fixed good evidence:** isolate inference errors. Compare
   local [Qwen3 4B Instruct/8B quantized tags](https://ollama.com/library/qwen3/tags)
   with identical evidence, prompt, output length, sampling and support labels.
   Use bounded context; don't load two large models at once without measured
   headroom. Require per-film claims, citations, supported contrast, limitations
   and a distinct writing suggestion. Then run the winner on retrieved evidence.
5. **Writer usefulness:** independent blind A/B on specificity, usefulness,
   trust, and whether a craft move survives scrutiny. Log reasons. Measure warm
   and cold retrieval and draft latency separately.

Proposed gates (product choices, **not** externally proven cutoffs): 100% of
evidence in the active pilot traces to verified/admitted descriptors, zero
wrong-film citations, ≥90% candidate facet recall, ≥80% complete evidenced
answers on all answerable held-out questions, and ≥80% correct qualification
or abstention on the negative/partial subset. All evaluated answers must
contain no material unsupported attribution; one critical error blocks
promotion regardless of average. Report numerator/denominator, intervals, and
individual difficult cases; 16/20 is an observed 80%, not proof of population
quality. Provisional budgets: evidence p95 ≤3 seconds warm, answer p95 ≤25
seconds warm (local), with cold starts separately reported. These express an
interactive product target, not forecasts. If answerability or sample counts
are too small, report inconclusive rather than silently shrinking the test.

Selection rule: choose 4B over a heavier passing model unless the heavier
model fixes a material, repeatable writer failure without creating a latency
or capacity regression beyond budget. Never select a failing model just
because it is faster, or select a model on one favorable example. With only
four held-out pairs, inspect paired differences and correlated errors; the
point estimate cannot establish a statistically reliable model winner.

Retrieval policy: begin with per-film lexical+dense pools and rank fusion.
Route by question as a **soft** preference for plot, craft or reception, not
a universal plot-only exclusion. Run a targeted ablation before adding a
4B reranker; only retain it if useful passages move into the displayed set
within the latency budget. Expand neighboring context for relationship/action
pairs; be explicit about unsupported assumptions. No automatic promotion of
semantic matches into canonical facts.

## 24-hour schedule and stop conditions

| Elapsed | Work | Artifact / stop rule |
| --- | --- | --- |
| H0–H3 | Recheck local disk, process/DB state, refresh inventory, freeze CSV/IDs, disposition candidates, outline question set. | Timestamped inventory, model space forecast and snapshot/rights queue. No destructive action while ownership or references are unclear. |
| H3–H7 | Verify pilot sources, write strict path mapping and positive/negative tests, normalize metadata, resolve pilot identity, prepare derived corpus and independently seal holdout. | A row for all 1,000 targets plus a source-approved pilot manifest. Stop expansion if exact identity or clearance is missing. |
| H7–H11 | Run a metered sample, then A/B embedding and lexical control on same verified pilot. | Record digest, bytes, chunks/sec, memory/swap, and ETA. Optional arm C only if it fits schedule and disk. |
| H11–H16 | Inspect development misses, change one retrieval factor at a time, score fixed-evidence generator. | Separate oracle, candidate, selected and draft reports; freeze candidate before opening holdout. |
| H16–H21 | Run sealed final evaluation and one real film intake-to-serving canary. Verify UI, cite actual passages, validate exact index activation and rollback. | Go/no-go by observed gates; do not reopen holdout for tuning. |
| H21–H24 | Deliver blind writer comparison if feasible, evidence-linked results, remaining work and verified changes. | Scale winning index toward the full reviewed 1,000 only if resources, rights, provenance and pilot gates pass; otherwise record ETA and blockers. |

Resource gate: maintain the existing **6 GiB** reserve after downloads and
temporary work, plus estimated additional vector/index/WAL/cache footprint.
At the measured 9.4 GiB free, a fresh 4.7 GB model alone would cross that
reserve; A might fit but not automatically once scratch space is counted.
Verify exact cached copies first. Use sequential model trials, a dedicated
model store, and retain reports/digests if an approved redundant weight is
removed. Never spend the reserve making the graph look complete. Measure
50–100 representative passages before projecting the full model run:
`elapsed = loading + chunks / observed throughput + validation`, then add
actual observed tail overhead and check the sprint clock. One worker per run;
persist IDs and logs, resume a known job rather than duplicate it.

Definition of done for the sprint: inventory and disposition log, versioned
corpus manifest and explicit exclusions, completed model/retrieval test
artifacts or evidence explaining why an arm could not run, real citations
and failure examples, separate pilot-vs-1,000 coverage, and a reasoned
ship/no-ship verdict. A passing small pilot is not a paid launch gate.
