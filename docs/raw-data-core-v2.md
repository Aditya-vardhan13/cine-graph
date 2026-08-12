# Raw-data core v2

## Decision

Build the catalog before intelligence. PostgreSQL is the system of record;
content-addressed object storage retains raw source payloads; graph and vector
indexes are later-derived read paths. The initial target is a validated
100-film English evaluation set and the design must serve 100,000 films.

## Assumptions challenged

| Assumption | Result |
| --- | --- |
| One agent or browser per title scales | It is non-repeatable, difficult to rate-limit, and loses source-version consistency. Use bulk dumps and bounded source tasks. |
| Robots permission alone permits reuse | Licence, terms, API policy, attribution, and retention scope also apply. |
| IMDb Top 1000 can be scraped | IMDb prohibits screen scraping and public movie-information databases using its non-commercial data. It requires a separate commercial licence. |
| A graph database is the core | Trustworthy evidence is the core. Indexed PostgreSQL claims and edges come first; export a graph only after measured need. |

## System design

```text
selection manifest -> source access policy -> raw ingestion run
       -> source object -> immutable source snapshot -> source assertion
       -> entity resolution -> normalized claim / typed edge
       -> rebuildable projections -> search, graph, vectors, intelligence
```

### Storage choice

PostgreSQL provides transactions, uniqueness, audit queries, full-text search,
JSONB source detail and future pgvector retrieval. A graph database now would
introduce a dual-write consistency problem. Raw payload bytes live outside
PostgreSQL under a content-addressed URI: `data/raw-snapshots/` locally and an
S3-compatible bucket in production.

## Durable tables

| Layer | Tables | Responsibility |
| --- | --- | --- |
| Source governance | `data_sources`, `source_access_policies` | Licence, permitted API/dump/HTML mode, robots and rate decision. |
| Ingestion | `raw_ingestion_runs`, `source_objects`, `source_snapshots` | Versioned manifest, source identity, every immutable source revision/hash/URI. |
| Evidence | `source_assertions` | Exact source property, statement path, raw value, qualifiers, rank and extractor version. |
| Identity | `canonical_entities`, `entity_aliases`, `entity_resolutions` | Language-neutral entities plus reviewable source-to-entity links. |
| Facts | `claims`, `claim_evidence`, `claim_qualifiers` | Normalized facts with a retained evidence path and queryable qualifiers. |
| Read models | `*_projection` tables | Rebuildable API/search/graph views; never the only truth. |

The existing film/person/credit/assertion tables remain compatibility
projections during migration and are not deleted.

## Field inventory

| Domain | Retained fields |
| --- | --- |
| Identity and title | source IDs; QIDs; page/revision; work type/status; canonical/original/regional/alternate/working/transliterated titles; language/script. |
| Release and production | release date precision, territory, release type, festival/platform, certification, runtime/version, language, country, genre, subject/keyword. |
| Credits | person or organisation; source role wording; normalized role; credited-as name; character; billing; department; voice/archive/uncredited flags. |
| Organisations and money | production company, distributor, studio, platform; budget/gross with currency, territory, date and reporting scope. |
| Technical and work links | format, colour, aspect, sound; sequel/prequel, remake, adaptation, source material, franchise, universe, character, setting. |
| Awards | awarding body, ceremony/year, category, recipient/work, result. |

Every value is a raw source assertion first. Normalized values retain source
statement evidence. Missingness is reported rather than guessed.

## Source plan

| Source | Role | Scale route | Decision |
| --- | --- | --- | --- |
| Wikidata | primary structured facts and identifiers | API for 100; official JSON dump and incremental dumps for 100k | CC0; adopt |
| Wikipedia / Wikimedia | cited narrative and supplementary context | API for bounded pilot; multistream/page-index dump at scale | CC BY-SA; retain revision and attribution separately |
| CMU Movie Summary Corpus | historical narrative / character reference | published archive | CC BY-SA; secondary, quarantined |
| IMDb | none | no scraper or non-commercial-dataset import | requires separate licence |
| TMDb, MovieLens, mirrors | none until specific rights approval | no foundation import | provenance/licence insufficient |

Every adapter needs an approved access-policy record. It stops on a denial,
rate limit, robots restriction, authentication wall, or incompatible licence.

## Scale and quality gates

1. Make a versioned, identifier-backed 100-film manifest; retain raw Wikidata
   entity JSON and every extracted statement.
2. Report identity conflicts and field coverage for titles, release events,
   credits, companies, work links, language/country and source revision.
3. Expand with the same checkpointed pipeline to 1,000 titles.
4. At 100k, filter the official Wikidata dump locally, retain dump checksum/date,
   and use incremental deltas—never 100k page crawlers.
5. Partition high-volume source assertions, claims and edge/credit projections
   only when measurement requires it.

The test 100 passes only with unique canonical IDs, retained snapshot hashes,
at least 95% title/year coverage, no published claim lacking `claim_evidence`,
and no unlicensed text or IMDb data.

## Primary references

[Wikidata downloads](https://www.wikidata.org/wiki/Wikidata:Database_download)
and [licensing](https://www.wikidata.org/wiki/Wikidata:Licensing) establish the
CC0 dump route. [Wikimedia API access](https://www.mediawiki.org/wiki/Wikimedia_APIs/Access_policy)
and [rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits)
govern API use; [Wikipedia reuse](https://wikimediafoundation.org/what-we-do/wikimedia-projects/wikipedia/)
is CC BY-SA. [IMDb’s policy](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX)
prohibits its scraping route.
