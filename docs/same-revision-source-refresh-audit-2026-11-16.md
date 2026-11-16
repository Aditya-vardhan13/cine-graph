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
