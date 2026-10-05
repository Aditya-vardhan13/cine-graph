# Data-source and crawler policy

## Phase A source: Wikidata

- **Content collected:** CC0 structured film metadata, people, credits, genres, countries, and identifiers.
- **Collection route:** the documented Wikidata Query Service API; no HTML pages are crawled.
- **Excluded from this structured adapter:** article text, plots, images/posters, subtitles, scripts, and other creative material. The separate Wikipedia research adapter has its own attribution and licence boundary below.
- **Access controls:** identifiable `User-Agent`, gzip support, one sequential request per second, stop on 401/403, and honor `Retry-After` on 429 responses.
- **Provenance:** every imported record carries a Wikidata entity URL, source, license, and ingestion-batch ID.

Wikidata makes its structured data available under CC0. The project retains a visible “Source: Wikidata” attribution even though it is not required by that license.

## Local IMDb non-commercial datasets

- **Content collected:** operator-supplied `title.basics`, `title.akas`, `title.crew`, `title.principals`, `title.ratings`, and `name.basics` TSV records. IMDb's public files do not supply plots, complete cast, exact release events, or career-impact analysis.
- **Collection route:** local files only. No IMDb HTML or hidden endpoint is scraped. A sparse local index is disposable; selected per-film source bundles are stored as immutable local snapshots before assertion extraction.
- **Rights:** IMDb permits these datasets for personal/non-commercial use under its [dataset terms](https://www.imdb.com/interfaces/). Raw files, snapshots and derivative assertions stay local and are never committed or deployed as a commercial corpus without appropriate rights.
- **Identity:** explicit IMDb IDs or exact title/year are accepted; fuzzy titles need an independent actor-credit anchor. Conflicts remain review tasks, not silent merges.

## TMDb developer API

- **Content planned:** credits with character names, release events, language, countries, production companies, alternate titles, and overview context via documented `/3/find/{external_id}` and `/3/movie/{id}` routes.
- **Collection route:** authenticated HTTPS API with the access token held in local `tmdb_api.env`, sequential requests, conservative pacing, `429` backoff and stop-on-denial. No TMDb HTML scraping.
- **Rights:** the developer API is [free for non-commercial use with attribution](https://developer.themoviedb.org/docs/faq); a revenue-generating deployment needs the appropriate commercial agreement. TMDb output stays in its own source snapshots and assertions, never merged into CC0 without provenance.

## Wikipedia narrative and filmography supplements

- **Collection route:** documented MediaWiki API revisions with an identifying user agent and sequential pacing, not HTML crawling.
- **Rights:** article revisions are retained as local, attributed CC BY-SA snapshots. Narrative passages and interpretations are not automatically operational facts.
- **Current supplement:** actor filmography rows can fill principal-credit omissions only when a film independently matches an IMDb-anchored explicit manifest entry. The row, revision, character text, and film identity remain inspectable.

## Approved narrative-reference source: CMU Movie Summary Corpus

- **Content collected:** English-language plot summaries plus their source-record metadata from the published archive.
- **Collection route:** an explicit archive download or an operator-supplied archive file; it is not fetched during application startup.
- **Rights and provenance:** CMU states that the corpus is released under CC BY-SA. Each retained document records its source revision, content hash, licence snapshot, and an English Wikipedia attribution URL.
- **Boundary:** this is a historical 2012 English-Wikipedia / Freebase reference layer. It does not overwrite canonical titles, release dates, credits, or box-office values from the CC0 fact layer.
- **Product use:** attributed reference material only. Semantic retrieval can suggest candidates, but a narrative similarity is never shown as a proven relationship or influence.

## Policy for every future HTML source

Before an HTML crawler is enabled it must:

1. Pass a source-specific terms/licensing review and record the decision in `data_sources`.
2. Request and parse that domain’s `robots.txt` with the project user agent.
3. Fail closed if `robots.txt` is missing, inaccessible, ambiguous, or disallows the target path.
4. Honor `Crawl-delay`, HTTP `429`/`Retry-After`, and the source’s documented rate limits.
5. Store the `robots.txt` URL, access decision, source URL, acquisition date, and content rights with its batch.

No collector may bypass a block, CAPTCHA, paywall, authentication wall, or robots restriction. A source that does not explicitly permit the intended collection is not used.
