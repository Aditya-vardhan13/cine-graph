# Narrative research layer

## Why this exists

A film page has richer material than a row of credits: plot mechanics,
production choices, reception, career milestones, criticism, cultural impact
and direct sequel/adaptation routes. Those materials are not interchangeable.
For example, a release date is a source fact, while a reading of *The Dark
Knight* as a war-on-terror allegory is an attributed interpretation.

The research layer preserves that difference before it is surfaced to a writer
or used for comparison.

## Data model

```text
immutable source snapshot (revision + licence + attribution)
  -> narrative passage (section path + ordered, readable chunk + citation markers)
    -> research answer (declared question + evidence class + review status)
      -> answer evidence (specific passage or structured source assertion)
```

`narrative_passages` only stores material from an attributable snapshot. Its
raw wikitext remains in the original source snapshot so a newer parser can be
replayed without refetching the page.

`research_answers` must be one of:

- `source_fact` — a directly recorded production, release, credit, award or
  lineage fact;
- `narrative_extraction` — a bounded reading of plot or source narrative;
- `derived_relation` — a transparent computation over evidence-backed facts;
- `attributed_interpretation` — an identified critic, scholar, publication or
  reception account;
- `semantic_candidate` — a retrieval lead requiring review before publication.

An answer cannot have no evidence target. A visible answer must additionally
pass review; the current pilot is correctly marked `review_required`.

## Ten-film pilot

The initial pilot deliberately varies franchises, adaptation, science fiction,
animation, action, social horror and nonlinear crime storytelling:

| Film | Questions | Source material retained |
| --- | ---: | --- |
| The Dark Knight | 8 | 72 passages / 24 sections |
| Batman Begins | 4 | 34 passages / 19 sections |
| The Dark Knight Rises | 4 | 50 passages / 21 sections |
| The Matrix | 4 | 55 passages / 27 sections |
| Blade Runner | 4 | 55 passages / 22 sections |
| 2001: A Space Odyssey | 4 | 72 passages / 34 sections |
| Mad Max: Fury Road | 4 | 36 passages / 20 sections |
| Get Out | 4 | 25 passages / 13 sections |
| Spider-Man: Into the Spider-Verse | 4 | 42 passages / 19 sections |
| Pulp Fiction | 4 | 61 passages / 23 sections |

That is 502 passages, 44 curated research answers and 230 passage-level
evidence links, all from retained CC BY-SA 4.0 English Wikipedia revisions.
The figures are reproducible with `app.services.wikipedia_research --quality`.

## Full English-1,000 extraction milestone

The same extraction contract has been applied to every film in the vetted
English-1,000 selection. It is a local database milestone, not a claim that all
films have the same depth of editorial interpretation.

| Check | Result |
| --- | ---: |
| Selected films with a retained revision | 1,000 / 1,000 |
| Films with one or more parsed passages | 1,000 / 1,000 |
| Narrative passages | 24,446 |
| Exact source section paths | 13,410 |
| Empty passages | 0 |
| Passages with attribution URL | 24,446 / 24,446 |
| Passage licence | CC BY-SA 4.0 |

The command uses the completed selection manifests to select QIDs, so it never
widens the corpus through a title search:

```bash
PYTHONPATH=backend python -m app.services.wikipedia_research \
  --ingestion-manifest /private/tmp/cinegraph-imdb-selection-100-v2.json \
  --ingestion-manifest /private/tmp/cinegraph-imdb-selection-9-retry.json \
  --ingestion-manifest /private/tmp/cinegraph-imdb-selection-900-v2.json \
  --ingestion-manifest /private/tmp/cinegraph-selection-9-repair-v3.json
```

The extractor is idempotent and commits per film. If a source-heading edge case
or an interrupted local database occurs, rerunning the command skips passages
already retained and resumes from the missing film.

## The Dark Knight example

The source lets us make useful but bounded cards, such as:

- story: Gotham's organised-crime campaign becomes an escalating test of law,
  public trust and moral limits;
- craft: the grounded crime-drama frame, IMAX and practical-effects choices;
- career: Ledger's performance, death before release and posthumous award chain;
- reception and legacy: separate commercial, critical, National Film Registry
  and later industry-interpretation records;
- analysis: parallel readings of escalation, surveillance, civic symbolism and
  morality—never a single imposed "meaning".

Each card links back to sections in the captured revision of
[The Dark Knight](https://en.wikipedia.org/wiki/The_Dark_Knight), rather than
presenting CineGraph's paraphrase as an unsourced fact.

## Retrieval and embeddings

Embeddings are useful once there is a licensed passage corpus. They will index
`narrative_passages` (with source revision and licence), retrieve candidate
comparisons, and require a reviewed research answer before a relationship is
shown as a claim. This preserves the distinction between "these passages sound
similar" and "these films are demonstrably related".
