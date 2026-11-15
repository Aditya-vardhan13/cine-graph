# Writer Wikipedia refresh: source review checkpoint

The sequential, robots-checked refresh completed on 15 November 2026 for the
996 entries passing the pinned mechanical identity audit. Four entries remain
outside this capture: *Lost in Translation*, *Minority Report*, *Talvar* and
*Gangs of Wasseypur 2*. They require separate identity/source review.

The checkpoint contains 996 `review_candidate` responses, totalling 500,812,793
uncompressed bytes. The captured HTML remains local; this result does not mean
the articles have been individually vetted, approved for model use, ingested,
embedded, or published. The capture was sequential, with at least one second
between requests; it stopped on low storage and resumed from its verified
checkpoint after space was freed.

## Read-only comparison

The source-bound v3 comparison checked all 996 retained captures against their
pinned prior snapshots and existing passage extractions:

- 987 have a story section in both versions.
- Six flag a possible story-length reduction for review: *Veer-Zaara*, *In a
  Lonely Place*, *Midnight Express*, *X-Men: First Class*, *3 Idiots*, and
  *My Sassy Girl*.
- *Pulp Fiction* needs a section-mix review: the earlier `plot` hierarchy
  includes character lists. Its difference is not automatically a plot loss.
- *Hamilton* gains a synopsis compared with its pinned older snapshot. Its
  separate source-only replay was already recorded in the earlier
  project plan; it is not approved for semantic use.
- *Fantasia* has neither a plot nor synopsis in either extraction; its
  anthology program needs a separate, context-aware treatment.

These are character-count and section-name diagnostics, not semantic quality,
identity, licensing, or retrieval judgments. The local report is
`data/evaluation/writer-source-audit/wikipedia-refresh-v1/story-delta-review-996-v3.json`,
SHA-256 `ffd657dfe75afadcf6189cdbb5d0b1db9448d2b6642ef4089cfd5ab8d684acaf`.
Original snapshots and previous review reports were not overwritten.

## Storage

The completed job started before the compressed-capture adapter and retained
uncompressed files, occupying approximately 480 MiB. New runs use gzip while
recording and checking the SHA-256 and byte size of the original response;
older uncompressed captures remain readable. One sampled article compressed
from 1,274,983 bytes to 209,015 bytes; this is not a measured corpus-wide ratio.
No existing source files were deleted or rewritten as part of this change.

## Next gates

Review the exceptional articles and film identities, determine permissible
source use with exact attribution, replay selected captures without replacing
historical evidence, and explicitly select eligible sources for the writer
collection. Only then build or update its local index and measure question-
conditioned retrieval and citation support on a separately reviewed test set.
The refresh alone is not a usable product release.

## Source-only two-film canary

The current-source resolver exposed a separate provenance issue: in a
non-random 20-film diagnostic, no current snapshot ID matched the pinned audit
snapshot; 19 had the same revision but a missing current source file, and one
had a verified newer snapshot. For *Avengers: Endgame*, the audited recovered
file is intact and all 37 extracted passage locator/ordinal/content hashes
match the missing-file current record. This does not recover the missing bytes
or imply that the two raw files were identical.

The guarded replay now permits that narrow situation only when the recovered
source file verifies, the source object and revision match, the current source
file is missing, and both complete passage projections match with their content
hashes independently recomputed. Other mismatches still stop the replay.
Separate PostgreSQL tests exercise the match and reject altered passage content
and revisions. The manifest preparer binds selected captures to their prior
snapshot and hash without copying their source bytes; it supports gzip and the
existing uncompressed captures.

The local source-only canary added refreshed snapshots for *Avengers: Endgame*
(revision 1383904568, 49 passages) and *The Godfather* (revision 1385766772,
51 passages). Both reruns were idempotent. No narrative-use decisions were
created for either snapshot, and neither was published or indexed as part of
this canary. Snapshot history is retained. This does not prove relevance,
legal clearance of every passage, or writer-facing quality. For reuse
considerations, Wikimedia's [developer guidelines](https://foundation.wikimedia.org/wiki/Legal:Wikimedia_Developer_App_Guidelines/en)
describe attribution, licence and share-alike requirements; individual source
and downstream usage still need review.

## Twenty-film development source expansion

The remaining 18 films in the existing ten-pair development question set were
replayed through the same source-only guard. Together with the two-film canary,
all 20 current selected snapshots passed a fresh stored-byte integrity check and
contain 1,047 source-linked passages in total. This includes *Her*, *WALL-E*,
*The Dark Knight*, *Spider-Man: Into the Spider-Verse*, *Interstellar* and
*Parasite*. All 18 new replays reported success; no source-use decisions exist
for any of these 20 current snapshots.

These are source preparation results only. The frozen development relevance
labels were authored against different revisions and must not be assumed valid
for these new passages without source-bound rebinding and review. The separate
held-out set remains separate. No new writer collection membership, embedding
index, or production retrieval accuracy claim follows from this expansion.

For the 20-question development subset, a source-bound, read-only comparison
located 36 of 39 previously reviewed quotations byte-for-byte in the new
revision passages. Three were not exact matches. Two of those have unique
whitespace-only candidates caused by paragraph breaks (*The Godfather* and
*No Country for Old Men*); the *Jaws* candidate also changes punctuation and
needs individual inspection. Offsets refer to the actual retained passages.
The old review and source fingerprints were checked, both old and new snapshot
files verified, and both revisions belong to the same source object. These
are candidate locations, not migrated labels, independent reviews, or a new
retrieval score. The local v2 report SHA-256 is
`d0c05dd41734632a703a02ee1d97555b458721db91155346980d0c808990657a`.

## Guarded source-only batch

The source-only batch selected the 987 entries whose automated comparison found
story sections in both revisions. This is a selection heuristic, not evidence
that the text is unchanged or accurate. The batch processed all 987: 937 new
snapshots were created, 20 earlier canary snapshots were reused, and 30 were
held for a current-versus-pinned source mismatch. The nine other article
comparison exceptions and the four original identity exceptions remain outside
this batch; categories have not been merged or silently approved.

An independent read-only verification checked all 957 created or reused
snapshot files against their stored hashes and byte sizes: 957 verified. These
snapshots have 23,218 source-linked passages and **zero** narrative-use
decisions. The 30 held candidates remain review-required. The source-only
checkpoint is local, SHA-256
`15a7c07a6b802d8c3bf5b21b0d687644d4948cacde402e8940880c9a2cfaa007`.
These counts do not establish passage accuracy, writer usefulness, source-use
approval, embeddings, or availability in the site.

Read-only follow-up of all 30 held candidates found an intact current source
and the same source object in each case, but a different revision than the
original audit baseline. The refreshed capture is newer than the current source
for 26; for four it has the same revision but different captured bytes. Eleven
of the 30 current passage projections match the older baseline by locator,
ordinal, and stored content hash; this alone does not establish source-byte
equivalence or approve a new revision. No held record was changed. Comparisons
against their actual current revisions are needed before any further replay.

### Follow-up against actual current revisions

The 30 held captures were compared against the actual verified current
snapshots, rather than the older audit baselines. All had story sections in
both versions under the same character-count heuristic. Twenty-six captured
revisions were newer and were replayed with manifests pinned to the actual
current snapshot ID, hash and revision. Their 26 stored source files verified,
and they added 653 source-linked passages with zero model-use decisions. Four
captures had the same revision as an existing verified source and were left
for review rather than creating redundant snapshots. Re-running the held
checkpoint processed no new records. This is source preparation, not a
semantic-quality or rights approval. The held replay checkpoint SHA-256 is
`5391a1455a68d11d0dc0554281eee5ef3e3b0485f57590683d87a8016085412c`.
The four same-revision existing sources were independently rechecked:
*Baahubali 2*, *A Wednesday!*, *KGF: Chapter 1*, and *Andaz Apna Apna* all
have verified current source bytes and 104 passages between them. Their current
snapshots have no semantic-use decisions; different bytes at the same revision
were not treated as proof of an identical raw response.

## Refreshed-source retrieval canary

In an isolated PostgreSQL schema, an explicit test-only approval allowed the
current plot passages for *Avengers: Endgame*, *The Godfather*, *Her* and
*WALL-E* to be chunked and indexed using local `qwen3-embedding:0.6b`
(Q8_0, 1,024 dimensions). The four articles produced 16 chunks. The first two
films returned plausible source leads for the user's family/conflict question.
For the user's *Her* / *WALL-E* loneliness question, *Her*'s leading passage
covered Theodore and Samantha, but the top *WALL-E* passage mostly described
events aboard the Axiom. A more pertinent passage about WALL-E's isolation and
meeting EVE appeared second. This is a real ranking failure in one inspected
case, not a representative accuracy rate or a resolved product issue.

The actual comparison HTTP route also returned a hybrid result when the test
container was configured with the local embedding endpoint. An earlier test
run without that endpoint correctly fell back to lexical retrieval; it was a
test-environment configuration issue, not evidence that hybrid ranking ran.
At the time of the initial canary, writer-index work was uncommitted. It was
subsequently committed after 21 focused tests, including isolated pgvector and
local Ollama checks. This does not imply the live API has been rebuilt, any working
corpus source approved, or a writer-facing result generated. Test-only
approvals do not carry into the working database. This diagnostic does not
justify changing ranking weights on its own; broader source-bound evaluation
is needed to avoid overfitting one example.

### Eight-film development diagnostic

An expanded isolated run indexed all selected article sections for eight films
in the existing 20-question development corpus: 474 eligible chunks with the
same local `qwen3-embedding:0.6b` model (digest
`ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d`).
The 20 questions were ranked before the previous review quotations were read.
For the 38 of 39 reviewed quotations with an exact or whitespace-only location
candidate in the new source revisions, the whole quotation was visible in:

| Method | First result | First three | Warm local p50 / p95 |
| --- | ---: | ---: | --- |
| Existing hybrid | 15 / 38 | 25 / 38 | 105.91 / 129.77 ms |
| Existing lexical | 9 / 38 | 14 / 38 | 26.55 / 37.48 ms |

Each question's timing includes the comparison call, not cold model load or
index construction. These are individual quote-visibility counts in a small,
previously inspected development set; multiple quotes can belong to the same
question. They are not 20-question pair success, answer correctness, user
utility, production latency or held-out accuracy. A candidate location in a
new revision still requires source-aware review. One unmatched quotation was
excluded and is not treated as a negative. No settings were changed on the
basis of these counts, and the isolated test did not approve working sources.

## Follow-up source exceptions

Two articles initially excluded by their recorded URL/title discrepancies were
recaptured through the robots-checked article fetcher. *Lost in Translation*
matched Wikidata Q107270 and Wikipedia page 369682; *Minority Report* matched
Q244604 and page 142049. Each capture was bound to the exact previously audited
source snapshot and replayed with the guarded same-revision recovery checks.
The newly stored sources verified and contain 59 and 39 passages respectively;
neither has a narrative-use decision. These page/QID checks do not resolve the
separate missing Wikidata source evidence in the original audit or approve
rights. *Talvar* remains a distinct identity issue.

Two plot-length exceptions were also inspected: *Pulp Fiction*'s older plot
hierarchy included character lists, and *X-Men: First Class*'s older plot
contained cast markup. Their refreshed snapshots were retained as source-only
records (69 and 45 passages) with verified bytes and no model-use decisions.
Five other shorter-plot cases remain for source-aware review; older snapshots
have not been removed.

Four additional missing current source files were replaced with retained newer
article snapshots, without deleting the older records: *Midnight Express* (19
passages), *My Sassy Girl* (21), *In a Lonely Place* (18), and *Fantasia* (70).
These are source captures, not assertions that each film's full research
needs are covered or that the content is approved for model use.

*Gangs of Wasseypur 2* has an existing active canonical entity but no legacy
film profile. Its current Wikipedia capture matches Q16248515 and page
36281191 and was bound to its reviewed prior source. An explicit entity-ID
override allowed source-only replay: the verified revision contains 21
passages. It did not create a film profile, approve narrative model use, or
resolve the outstanding metadata projection. The override rejects missing or
different IDs and cannot be used for an existing film profile; its checks
were exercised against isolated PostgreSQL using retained article bytes.

## Current-source coverage recheck

After the above source replays, a read-only audit over the same pinned 1,000
film identities found 1,000 current Wikipedia source files whose size and hash
verify, and 24,455 current passages on those article objects. None of these
current snapshots has an eligible semantic-use decision. *Fantasia* has no
standard plot/plot-summary/synopsis section, and *Gangs of Wasseypur 2* still
lacks a legacy Film profile. The audit is reproducible with
`python -m scripts.audit_current_writer_sources <identity-audit> --sha256 <digest>`;
it uses current-extraction selection and does not write to the database. Its
counts do not establish article identity approval, story completeness, factual
accuracy, suitability for a particular question, or retrieval quality.
The previously noted *Talvar* QID discrepancy remains unresolved even though a
current stored file for its existing source object passes the byte-integrity
check. Wikipedia articles can also contain third-party quotations; the page's
general text license alone is not a rights determination for every quotation.

### Original question: isolated API recheck

The retained-source two-film canary was rerun with the user's original
family/injustice question, local `qwen3-embedding:0.6b`, and a separate
`cinegraph_test` schema. The leading *Endgame* passage includes Nebula,
Gamora and Thanos, while the leading *Godfather* passage describes Michael
protecting Vito and killing Sollozzo and McCluskey. These are plausible leads,
but each is long and neither alone resolves the question. This single known
development case is not an accuracy score or proof of a useful final answer.
No working-corpus permissions were granted.

The first run exposed a local configuration mistake: the direct test passed
the host Ollama URL explicitly, while the HTTP handler inherited the container
default `127.0.0.1` and fell back to lexical retrieval. Setting both
`CINEGRAPH_TEST_OLLAMA_URL` and `OLLAMA_BASE_URL` to the reachable host URL
made the real HTTP check return hybrid results. This distinction matters when
running the local pilot; an HTTP 200 or a passing direct service call is not
proof that the API actually used embeddings.

### Talvar identity cross-check

The two Wikidata items were checked again against the live source pages.
[Q17492514](https://www.wikidata.org/wiki/Q17492514) describes the 2015 Meghna
Gulzar film and records its director, writers, cast and release information.
[Q141776793](https://www.wikidata.org/wiki/Q141776793) describes a 2015 film
by the same director and has the English Wikipedia sitelink for
[*Talvar (film)*](https://en.wikipedia.org/wiki/Talvar_(film)); the article
itself links to Q141776793. This is strong evidence of a duplicate-item
candidate, but the two identifiers have not been merged by Wikidata, and the
second item has very few statements. The discrepancy is not a failed file
integrity check, nor is it permission to rewrite the current source identity.
Keep the older source and flag the current article for a separately recorded
identity resolution rather than silently relabelling its QID.

The current article was then captured with the existing robots-checked
review-only fetcher. It matched page ID 43433839 and Q141776793 at revision
1380716655; its exact HTML SHA-256 is
`c4e625a99d4035b870b80b86c95460c1226c664abc02a444acb226cc573798f3`.
The local manifest remains marked `review_required` for identity and rights,
with `product_ingested` false. The prior Q17492514 association and article
snapshot were not replaced, and no operational assertions were created.

### Smaller-chunk development comparison

An isolated experiment used the same eight refreshed articles, 20 known
development questions and local `qwen3-embedding:0.6b` model. The default
300-token target produced 474 indexed chunks; a 120-token target with 30-token
overlap produced 1,021. On 38 reviewed quotes that could be located in the
refreshed passages, the default hybrid results contained the complete quote
15 times at rank one and 25 times in the top three; the smaller chunks contained
it 9 and 21 times respectively. Warm local hybrid p50/p95 were 103.84/133.09 ms
and 113.15/140.98 ms. These are 20-query development diagnostics, not a
representative accuracy estimate or production latency measurement.

The comparison penalizes a smaller chunk when a reviewed quote crosses chunk
boundaries, even if partial evidence is present; it does not score semantic
relevance or completeness. The smaller top result was visibly better for the
*Her* / *WALL-E* loneliness example, but dropped the Nebula family conflict
from the first *Endgame* result. Given the lower full-quote visibility and
roughly 2.15 times as many vectors, do not switch the live chunk size based on
this run. A span-aware or parent-context comparison and an independent
writer-question evaluation remain necessary. The alternative chunk profile is
only selected explicitly by the local canary; the writer index default remains
unchanged, and no working-corpus index or approvals were created.
