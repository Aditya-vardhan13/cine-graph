# Scholarly discovery queue v1

This queue finds potential criticism for the frozen `english-1000-retained-narrative-v1` film collection. It is a review queue, not an intelligence layer and not a source of movie facts.

## What is stored

- The canonical film identity, provider work ID, query title, matched work title, landing URL, matching method and score.
- An immutable snapshot of **bibliographic metadata** with source, retrieval run, content hash and licence/provenance note.
- A replayable query outcome for every film: `complete`, `no_candidates`, `skipped_ambiguous`, or `failed`.

Every candidate begins as `pending`. An editor must establish that the work concerns the intended film and separately decide whether its licence permits any use beyond a link before it can become a `CriticalWork`.

## Providers

| Provider | Purpose | Stored scope | Live operating rule |
| --- | --- | --- | --- |
| OpenAlex | Scholarly work discovery | CC0 work metadata; no paper retrieval | Sequential, stop immediately on 403/429. The current run is paused until OpenAlex's explicit `Retry-After` period expires. |
| Crossref | Independent scholarly metadata discovery | Bibliographic metadata only; abstracts are discarded before persistence | Public pool, one sequential list query every two seconds (30/min), below Crossref's documented one list-query/second public ceiling; stop immediately on 403/429. |

Crossref's API documentation says that most metadata can be used broadly, but warns that abstracts may be copyrighted. Therefore the Crossref adapter requests a search response but sanitizes each record before it is ever written: it retains DOI, title, authors, publication fields, venue, publisher, deposited licence metadata and citation count; it drops abstracts and does not follow full-text, PDF, image, or video links. [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)

Crossref recommends a valid `mailto` parameter for its polite pool. CineGraph does not invent a contact address. Until one is configured by the operator, it stays in the public pool at the slower fixed pace above. Current list-query limits and the hard-stop behaviour are documented by [Crossref's July 2026 rate-limit notice](https://community.crossref.org/t/refining-rest-api-limits-for-improved-stability-and-reliability/16137).

## What this deliberately does not do

- It does not scrape or download articles, essays, PDFs, videos, or images.
- It does not copy a reviewer's analysis into a film record.
- It does not use semantic similarity as evidence that an article discusses a particular film.
- It does not turn a discovered licence field into reuse permission without work-level editorial review.

This boundary lets later curation connect a critical argument to narrative or factual evidence while preserving the difference between a critic's interpretation and CineGraph's canonical data.
