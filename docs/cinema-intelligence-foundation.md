# Cinema intelligence foundation

## The product question

CineGraph should answer: **what is genuinely relevant about this film to this
creative or production decision?** It is not a title directory, a trivia
generator, or a generic “films like this” score.

The observation “a dispossessed heir returns to claim power” is useful, but
only as one possible relation. The same investigation may need to surface an
adaptation route, an original creative team returning, a franchise handoff, a
release-era shift, a technical collaborator, a setting, an award circuit, or a
semantic narrative candidate. Those are different statements and must never be
collapsed into one percentage.

## Assumptions challenged

| Assumption | Why it fails |
| --- | --- |
| Any 1,000 English-language films are a useful foundation | A database offset has no editorial or product meaning; it misses obvious anchor titles. |
| An IMDb Top 1,000 import is the solution | CineGraph cannot scrape or import IMDb data under its data-access terms, and popularity alone does not create useful relations. |
| One similarity score can explain relevance | A shared actor, direct sequel, shared editor, thematic candidate, and adaptation are different claims with different evidence requirements. |
| Vectors can discover facts | Vectors retrieve possibly relevant documents; they cannot prove influence, lineage, plagiarism, or factual metadata. |

## Fundamental truths

1. Every useful relation has a **relation type**, a **scope**, and evidence.
2. The value of a reference catalog is measured by coverage of the decisions
   users make—not by a hidden ordered list.
3. Pairwise comparisons grow quadratically. We must retrieve candidates first,
   then compute or review a small number of typed cards.
4. A catalog spanning recent cinema needs deliberate time coverage. A single
   global popularity proxy over-selects one period.

## Rebuilt data foundation

```text
CC0 canonical facts (Wikidata) ──> typed assertions ──> film/person/work projections
                                          │
versioned reference collection ──────────┘
                                          │
licensed narrative references ──> embeddings ──> candidate queue
                                          │                 │
human / deterministic reviewer ──────────┴────> typed, evidenced insight card
```

### English 2000–2025 Reference Shelf

The first operational collection has a fixed rule and a visible version:

- English original-language films, released between 2000 and 2025;
- an equal per-year allocation, with the remainder assigned chronologically;
- within each year, ordered by Wikidata cross-language sitelink coverage;
- every membership retains its position, sitelink signal, source, and
  collection version.

This creates a broad, reproducible 1,000-film *reference shelf*, rather than
claiming an unlicensed IMDb ranking. It intentionally has a second safety net:
named must-have titles may enter a separately-labelled editorial anchor set,
with the reviewer and rationale retained. The API must show the collection
name—not imply that either set is a universal quality ranking.

## Relation families

| Family | Example | Evidence rule | UI treatment |
| --- | --- | --- | --- |
| Direct work route | sequel, remake, adaptation, series membership | explicit typed source statement | fact card |
| Creative engine | same director/cinematographer/editor/producer team | exact credits and deterministic formula | derived card |
| Production & release context | country, runtime, release route, award, company, technology | source facts with qualifiers | fact/context card |
| Franchise & universe | property, character, fictional universe | explicit source property only | fact card |
| Semantic narrative | “rightful return” expressed across different settings | permitted document retrieval + human review | editorial candidate/card |
| Formal similarity | pacing, genre blend, period, runtime, form | declared feature comparison | context filter, never lineage |

The next Wikidata adapter pass adds typed properties for production company,
distributor, award, based-on / source work, fictional universe, characters,
locations and other documented film metadata. Each is kept as an assertion with
the original property ID and qualifiers; only selected projections become UI
cards.

## Embedding boundary

Embeddings will operate on permitted, licence-separated narrative documents and
eventually editorial abstracts. They produce a ranked review queue with the
retrieval model, source documents, query embedding version, and threshold
stored. A published card needs a human/editorial decision or a deterministic
formula plus retained evidence. It may say **“narrative candidate to inspect”**
until reviewed; it cannot say “these films share the same story” as a fact.

## Measurable gates

| Gate | Observable outcome | Exit criterion |
| --- | --- | --- |
| R1 | 1,000 visible 2000–2025 shelf members | date distribution has all 26 years; all members have provenance |
| R2 | Anchor coverage | named anchors such as *Interstellar* and *The Dark Knight* are searchable with correct display dates and credits |
| R3 | Typed metadata graph | every displayed relationship shows its family and evidence URL |
| R4 | Useful relation cards | 50 cards across at least five families; blind reviewer says they are useful more often than genre-only comparisons |
| R5 | Semantic review queue | vectors return candidates with source and model version; no unreviewed candidate is presented as a fact |

## Remaining uncertainty

Sitelink coverage is a transparent availability signal, not an artistic-value
metric. It will be evaluated against a written anchor checklist. If it creates
meaningful gaps, the fix is a labelled editorial anchor collection—not silently
changing the selection rule or pretending it is an objective top-1,000 list.
