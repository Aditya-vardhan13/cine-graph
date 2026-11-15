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
