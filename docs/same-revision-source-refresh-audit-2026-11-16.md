# Same-revision Wikipedia refresh audit

Two retained HTML captures were checked against their current local Wikipedia
snapshots: *Baahubali 2: The Conclusion* (Q21001674, revision 1376668137) and
*KGF: Chapter 1* (Q21646605, revision 1375167866). For both films, the
concatenated plot text matched exactly after Unicode NFC and whitespace
normalization. This does not establish equivalence of the complete articles.

The current HTML extractor deliberately excludes tables. The older Baahubali 2
extraction includes a distribution table, and KGF's includes an awards table;
the HTML extraction omits both. Baahubali 2's box-office section was also
shorter in the comparison. The current sources were therefore **not replaced**.
The two other candidates previously flagged for markup, *Veer-Zaara* and
*3 Idiots*, also require separate content review; their refreshed stories did
not meet the exact-comparison condition.

`prepare_same_revision_refresh.py` prepares a review-only manifest, not an
ingestion or rights approval. It requires exact current snapshot and capture
identity, verified bytes, matching revision and normalized plot, and rejects
sections with less than 75% of their former character count. The section check
is only a conservative warning screen, not proof of content equivalence or a
license determination. Any accepted manifest remains subject to the existing
replay, rights and corpus-membership guards.

Next: design a provenance-preserving extraction for relevant tables, including
headers, row relationships, citations and duplicate handling; compare the
result against retained sources before any refresh. Avoid treating raw table
rows or generated summaries as reviewed facts.

## Review-only table extraction

An offline, versioned adapter now retains `wikitable` captions, rows, cells,
cell kind, explicit row/column spans, scope and cell citation marker IDs.
Nested tables and visual content are flagged; spans are not automatically
expanded into inferred relationships. Each local output records the source
URL, QID, page and revision IDs, capture and checkpoint hashes, and remains
marked for identity and rights review. It does not write to the database,
create retrieval passages, or prove that all table content was captured.

On the two pinned HTML captures, the adapter produced two tables for
Baahubali 2 (9 distribution rows and 15 box-office rows) and one for KGF
(29 awards rows). No nested-table or visual-content warning was emitted for
these three. This is structural extraction, not validation of award winners,
distributors, row-span interpretation or citation support. Those comparisons
and a policy for citation-bearing table-derived evidence remain necessary;
neither source refresh is promoted. The outputs are local and immutable:

- Baahubali 2, v2 table review SHA-256 `2dc44b2c42fc2f9a0337c540be90978673f25bd4f5cdb1c5283972e26ccc4892`.
- KGF Chapter 1, v2 table review SHA-256 `bd6e0a497ae606388984a29b79481ea1013e1b98113f37fa84676636e1ef9397`.

The test suite checks retained-source identity and hashes, table structure,
spans, citation markers, explicit review status and malformed spans. It is not
an independent completeness audit. Relevant parser and isolated replay tests:
24 passed on 16 November 2026.
