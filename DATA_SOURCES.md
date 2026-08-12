# Data-source and crawler policy

## Phase A source: Wikidata

- **Content collected:** CC0 structured film metadata, people, credits, genres, countries, and identifiers.
- **Collection route:** the documented Wikidata Query Service API; no HTML pages are crawled.
- **Excluded:** Wikipedia article text, plots, images/posters, subtitles, scripts, and any other copyrighted creative material.
- **Access controls:** identifiable `User-Agent`, gzip support, one sequential request per second, stop on 401/403, and honor `Retry-After` on 429 responses.
- **Provenance:** every imported record carries a Wikidata entity URL, source, license, and ingestion-batch ID.

Wikidata makes its structured data available under CC0. The project retains a visible “Source: Wikidata” attribution even though it is not required by that license.

## Policy for every future HTML source

Before an HTML crawler is enabled it must:

1. Pass a source-specific terms/licensing review and record the decision in `data_sources`.
2. Request and parse that domain’s `robots.txt` with the project user agent.
3. Fail closed if `robots.txt` is missing, inaccessible, ambiguous, or disallows the target path.
4. Honor `Crawl-delay`, HTTP `429`/`Retry-After`, and the source’s documented rate limits.
5. Store the `robots.txt` URL, access decision, source URL, acquisition date, and content rights with its batch.

No collector may bypass a block, CAPTCHA, paywall, authentication wall, or robots restriction. A source that does not explicitly permit the intended collection is not used.
