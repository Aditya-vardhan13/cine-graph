# Evidence preprocessing v1

## Decision

Before CineGraph embeds anything, it materialises a versioned, source-linked
retrieval unit from licensed narrative passages. The first run operates only on
the explicit `english-1000-retained-narrative-v1` collection and English
`NarrativePassage` rows whose retained source snapshot is attributable under
`CC BY-SA 4.0`.

This is a text preparation step, not intelligence. A chunk cannot create a
canonical fact, a graph edge, a theme label, or a displayed insight.

## Why this shape

The raw facts are fixed:

- one source passage may be too large for a retrieval model;
- a semantic result must always resolve to a licensed source revision;
- chunking rules and embedding models will change independently;
- identical text can appear in two source contexts and both contexts matter.

So raw `NarrativePassage` rows remain unchanged. `EvidenceChunk` records the
derived text, source snapshot, passage, section, subject film, quality state,
and deterministic configuration hash. Exact duplicates are retained with their
own lineage and link to the first eligible canonical chunk; they are not
silently deleted.

## v1 policy

- Sentence segmentation: `spacy.blank("en")` with the rule-based sentencizer.
  It downloads no language model and makes no linguistic interpretation.
- Normalisation: Unicode NFC plus whitespace collapse. The source passage is
  never overwritten.
- Target / hard maximum: 300 / 360 spaCy token estimates.
- Overlap: trailing whole sentences covering about 50 token estimates.
- The overlap is dropped for a boundary when retaining it would breach the
  hard maximum; the next whole sentence remains intact in its own chunk.
- Minimum: 40 words. Smaller chunks remain stored as `excluded` with a reason,
  so corpus loss is visible.
- A sentence over the hard maximum is kept intact and stored as `excluded`
  instead of being split in the middle of a claim. A future specialised
  long-form policy must be versioned separately before it can enter an index.
- Eligibility requires an attributable source snapshot with an allowed licence.

`token_count_estimate` is intentionally not called a model token count. The
future selected embedding model's tokenizer will be measured separately.

## Operations

Run only after the corpus boundary exists:

```sh
PYTHONPATH=backend conda run -n cine-graph python -m app.services.evidence_preprocessing \
  --collection english-1000-retained-narrative-v1 --build --report
```

The command is resumable for the exact configuration. It creates no external
network traffic and does not modify source snapshots or operational facts.

## Quality gate before embeddings

An embedding model may be evaluated only when the report shows:

1. every collection film has at least one eligible chunk, or every exception is
   explicitly listed and repaired at the source layer;
2. chunk-size and exclusion distributions have been inspected;
3. duplicate rate is known and only eligible canonical chunks are selected for
   the first index;
4. every selected chunk resolves to its passage, source snapshot, attribution
   URL, and licence; and
5. a measured retrieval evaluation set exists. Similarity remains a candidate,
   never proof of a relationship.
