# Indian film corpus pilot: local evidence audit (2026-10-05)

This is an audit of source coverage in the local database, not a claim that
the facts, film selection, or writer-facing answers are independently correct.
The 500-film cohort is a cross-language research sample selected from
Wikidata candidates and local IMDb audience signals; it is **not** an
authoritative greatest-films ranking. The selection manifest and row-level
report remain local with the corpus.

| Gate | 500-film cohort | Released Allu Arjun features |
| --- | ---: | ---: |
| Films in collection | 500 | 26 |
| IMDb source snapshot | 500 | 26 |
| Wikidata snapshot with matching IMDb identity | 500 | 26 |
| TMDb snapshot with matching IMDb identity | 499 | 26 |
| Any attributable narrative passage | 500 | 26 |
| Full plot passage | 488 | 26 |
| Production passage | 364 | 22 |
| Reception passage | 415 | 24 |
| Legacy or impact passage | 165 | 5 |
| At least one character-named credit | 499 | 26 |
| Identity conflicts in active reviewed assertions | 0 | 0 |

The audit reports 18 of the 500 films with at least one explicit gap. Twelve
lack a full plot passage: Achena Uttam, Adavi Kaachina Vennela, Balak Palak,
Cyanide, Distant Thunder, Gangs of Wasseypur, Happy Days, Hoy Maharaja,
Long Drive, New Delhi, Sarsenapati Hambirrao, and Wheel Chair Romeo. A TMDb
overview, where present, is short contextual text and is **not** counted as a
full plot. Six films lack IMDb character names; TMDb resolves five of those.
Haati Haati Paa Paa has no character-named credit from either source.
Long Drive is the one film without a verified TMDb match; a similar title is
not enough to attach a TMDb record. The two Wikidata items without an enwiki
sitelink are kept unlinked rather than guessed.

A second, read-only check found 13 cross-source metadata disagreements in the
500-film cohort: 12 IMDb start-year versus TMDb primary-date year differences,
and one original-language difference. The 26-film Allu Arjun collection has
none under these specific comparisons. These are review leads, not automatic
corrections. For example, *Hazaaron Khwaishein Aisi* has a 2003 festival
context in its [Wikipedia article](https://en.wikipedia.org/wiki/Hazaaron_Khwaishein_Aisi)
and an April 2005 Indian release according to
[Bollywood Hungama](https://www.bollywoodhungama.com/movie/hazaron-khwaishein-aisi/cast/),
so a single unqualified “release year” loses information. The 1957 date for
*Do Ankhen Barah Haath* is supported by an
[Indian government film-awards catalogue](https://dff.nic.in/images/Documents/87_30thNfacatalogue.pdf),
whereas the retained TMDb primary date yields 1960; this deserves source
review before any displayed date is changed. The local profile calls *Adavi
Kaachina Vennela* Telugu, consistent with its
[IMDb film page](https://www.imdb.com/title/tt3805052/) and a
[verified distributor upload](https://www.youtube.com/watch?v=O506o_V0GZ0),
while TMDb's original-language assertion says English. The source conflict
remains visible rather than silently choosing a winner.

The next quality gate is a manual spot check across languages and decades:
verify title, year, original language, lead cast with roles, full-plot scope,
and attribution against the retained source revision; record corrections as
reviewed source-backed assertions. Then evaluate writer questions against
this cohort before exposing it as a trusted research catalog. Missing
production, reception, and impact passages are coverage gaps, not fabricated
negative claims. Commercial deployment remains blocked on the source-rights
review in [DATA_SOURCES.md](../DATA_SOURCES.md).
