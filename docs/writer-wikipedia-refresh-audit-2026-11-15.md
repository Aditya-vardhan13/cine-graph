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
