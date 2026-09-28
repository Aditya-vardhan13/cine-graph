# Legacy profile release-date audit, 2026-09-29

Scope: read-only screening of the local `cinegraph` database; not a correction
job or a claim that every Wikidata statement is independently verified.

Of 1,226 legacy `Film` rows, 127 have a linked operational `release_event`
assertion with a day-precision Gregorian date. A screening comparison found
103 whose stored legacy `Film.release_date` differs from the earliest such
asserted date. This is substantial projection drift, not one Batman typo.

For example, the local legacy profile for *The Dark Knight Rises* says
2022-10-06. Its retained operational assertions include 2012 dates, and the
[Wikidata item](https://www.wikidata.org/wiki/Q189330) lists 2012 releases as
well as a later Saudi Arabia release in 2022. The writer research read model
uses its existing conservative `display_metadata` policy and returns 2012 as
the earliest recorded release year.

The product now displays the research year when available and explicitly
flags a disagreement on the profile, with a link to source evidence. It does
not rewrite an old row or silently promote prose. Release-era comparison
signals now require admitted source assertions for **both** films; a legacy
date alone cannot supply that signal. The homepage's legacy metadata cards no
longer present an unreviewed year as if it were the canonical release year.

Remaining debt: the older `/films` catalog still stores and returns the
legacy date, so its date ordering and decade filter can be wrong. The writer
library search uses the separate canonical research collection. A future
versioned profile projection should carry its own assertion IDs and date
precision, then retire the legacy date as a display authority. Do not bulk
rewrite `Film.release_date` without that provenance and regression gate.
