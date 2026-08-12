# English Corpus v1: research decision record

**Status:** research complete enough to begin a small, auditable prototype. This
is not approval to bulk-import every listed source.

## First-principles product test

The product's job is not to tell a writer that two films share a genre or cast
member. It must help them make a story decision in their own draft. Therefore a
reference-film connection is useful only when it has all three of these parts:

1. a specific, typed connection;
2. inspectable evidence and provenance; and
3. an explanation of the craft or development question it can illuminate.

For example, a franchise order can support a question about escalation across
installments. A shared writer-director partnership can support a question about
recurring collaboration. A semantic plot match may suggest a comparison, but is
not itself a fact and must not be displayed as one.

The smallest useful v1 is not a global movie database. It is a deliberately
selected English reference corpus with enough reliable evidence to power 25
high-quality connection cards and a visible corpus-quality dashboard.

## Source decision register

| Source | What it contributes | Rights/access finding | v1 decision |
| --- | --- | --- | --- |
| [Wikidata dumps](https://www.wikidata.org/wiki/Wikidata:Database_download) | canonical entity IDs, names, credits, explicit work relationships, statement qualifiers and references | structured data is CC0; JSON/RDF dumps are the recommended stable bulk interface | **Adopt as canonical fact layer** |
| [CMU Movie Summary Corpus](https://www.cs.cmu.edu/~ark/personas/) | 42,306 plot summaries; movie metadata; character-to-actor alignments | CMU states CC BY-SA. Plots are from the 2012 English Wikipedia dump and metadata is from 2012 Freebase | **Adopt as an attributed historical narrative-reference layer**, subject to product licence review before public redistribution |
| [Wikimedia APIs / dumps](https://www.mediawiki.org/wiki/Wikimedia_APIs/Content_reuse) | fresh, cited enrichment for selected titles | content licences vary; most English Wikipedia text is CC BY-SA. Attribution, modification notices, and share-alike obligations apply | **Use selectively**, with page revision and licence captured; prefer dumps/API over HTML crawling |
| [MPST](https://huggingface.co/datasets/cryptexcode/MPST) | roughly 14K plot synopses and fine-grained tags | the hosted card says CC BY 4.0, but its records identify IMDb as a synopsis source. A repository-level label does not establish downstream text rights | **Hold** until primary-source provenance is confirmed |
| [Cornell Movie-Dialogs](https://convokit.cornell.edu/documentation/movie.html) | dialogue exchanges and character conversation structure | raw dialogue is extracted from movie scripts; no product-ready content licence was established in this review | **Do not ingest** |
| [MovieSum](https://huggingface.co/datasets/rohitsaxena/MovieSum/blob/main/README.md) | screenplay structure research reference | CC BY-NC 4.0 | **Research only; do not product-ingest** |
| [IMDb data](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX) | extensive metadata and ratings | non-commercial terms prohibit screen scraping and public movie-information databases from the data | **Exclude** |

Every future web collector needs a stored, source-specific decision covering
terms, robots.txt, licence, attribution, request identity/rate behaviour, and
the exact fields retained. A public page is not by itself permission to crawl
or retain its content.

## CMU corpus inspection (2026-08-12)

The downloaded archive was inspected rather than treated as a black box. It
contains 81,741 movie metadata rows, 42,306 plot rows, and 450,669
character-to-actor rows. After joining by the Wikipedia movie ID, 24,776 films
are marked `English Language` and have a plot. Of those, 24,196 have a release
date and 6,727 have a box-office value.

This makes the source broad enough for narrative retrieval and character
experiments, but proves that box office is too incomplete to be a default
comparison feature. The date distribution is also uneven: the 2000s account
for 6,841 English plots, while 2010-2012 account for only 1,550. Sampling and
evaluation must therefore be stratified by decade rather than driven by source
frequency.

## Corpus boundaries

### Canonical facts

The canonical film record comes from Wikidata, not from a summary dataset.
Import full statements rather than only truthy values wherever the field can
have competing values. In particular, do not collapse release dates while
reading source rows.

```text
Film
  ├── external identifiers (Wikidata QID, Freebase ID where available)
  ├── title / aliases / language / country
  ├── release events (one row per source claim, territory and date)
  ├── credits (role, character, order, source claim)
  ├── explicit work relationships
  └── provenance assertions
```

`release_event` needs a selection policy, not an accidental `min()` or
last-row-wins value. The public display date should state its policy, such as
"earliest known public release", and retain all source events for inspection.

### Narrative reference data

CMU data is valuable precisely because it supplies plot text and named
characters at scale, but it is historical. Store it separately from canonical
facts as a source document with:

```text
film_candidate_id
source_document_id
source_revision_or_dump_date = 2012-11-02
licence = CC BY-SA
attribution_url
text_hash
access_scope
```

Never silently overwrite a canonical title, release date, cast credit, or box
office value with this source. Its Freebase movie ID is a strong reconciliation
key because Wikidata exposes it as [P646](https://www.wikidata.org/wiki/Property:P646).

## Reconciliation policy

1. Match CMU movie records to Wikidata by exact Freebase ID / P646.
2. If unavailable, resolve through a current Wikipedia sitelink plus exact
   title, release year, and language.
3. If still unresolved, compare a compact credit signature (director plus lead
   cast) and create a review candidate, never an automatic merge.
4. Publish only exact matches and manually approved candidates. Retain merge
   method, confidence, reviewer, and rejected alternatives.

This prevents the same-title and remake errors that make a relationship graph
look convincing while being wrong.

## Relationship taxonomy

Only relationship types with distinct semantics should be shown as facts.

| Family | Relationship examples | Writer-facing question |
| --- | --- | --- |
| Work lineage | follows / followed by, part of series, remake, adaptation, based on | What changes when a story engine is carried into another installment or form? |
| Creative lineage | first collaboration, recurring writer-director pair, actor-director run | Which creative partnership repeatedly works on this kind of material? |
| Production context | country/language route, release-event sequence, sourced commercial milestone | What was the project context, and how confidently can we claim it? |
| Narrative pattern | protagonist goal, pressure source, reversal, reveal, causal dependency | What transferable mechanism can a writer test in their own outline? |
| Semantic candidate | plot/character pattern neighbour from an embedding | What should a researcher inspect next? Never display this as a proved influence. |

Wikidata directly supports examples such as [follows (P155)](https://www.wikidata.org/wiki/Property:P155)
and [based on (P144)](https://www.wikidata.org/wiki/Property:P144). Their
incompleteness is a coverage limitation, not permission to infer a stronger
fact. Relationships must carry `assertion_kind` (`source_fact`, `derived`, or
`editorial`), evidence, confidence, and source references.

## Graph and vector responsibilities

PostgreSQL remains the source of truth. The relationship tables are the graph
for v1; no separate graph database is justified until measured traversal
workloads exceed what indexed relational queries handle well.

pgvector is appropriate only after a permitted text layer exists:

```text
permitted plot / user-owned scene
  -> chunk or structured narrative summary
  -> embedding
  -> candidate retrieval
  -> evidence-backed graph or source inspection
  -> writer-facing explanation
```

An embedding can retrieve a possible analogue. It cannot prove that two films
share a device, that one influenced another, or that an industry milestone is
true.

## Visible Phase-A outcome: Corpus Quality Board

Before redesigning the explorer again, expose a small page that makes the data
honest and reviewable:

- selected title count by decade, genre, and release country;
- exact / reviewed / unresolved CMU-to-Wikidata matches;
- field coverage for dates, writers, cast, characters, and explicit work links;
- relationship counts by type and assertion kind;
- every source's licence, dump/revision date, and provenance link;
- a sample of connection cards, each with its evidence and a writer question.

## Prototype acceptance criteria

The first import should be a stratified, reviewable selection, not 42,306
records. It is ready for a product experiment when it contains:

1. 500 English-language feature films selected across decades and major genres;
2. exact or manually approved entity reconciliation for every published film;
3. retained release events and an explicit display-date policy;
4. at least 100 explicit source-backed work/creative relationships;
5. 25 human-reviewed narrative connection cards, each explaining a craft
   question rather than merely presenting a similarity score; and
6. a documented removal/reimport path for any source whose rights decision
   changes.

Only then should embeddings be evaluated against a small editor-curated set of
"useful analogue" judgments. If retrieval does not improve those judgments, it
does not belong in the product yet.
