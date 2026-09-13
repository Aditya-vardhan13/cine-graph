# Source assertion projection v1

Status: implementation gate; run against the retained 1,000-film local corpus
before enabling structured comparison synthesis.

## Outcome

This projector closes the raw-to-operational evidence gap without introducing
a second fact store:

```text
immutable SourceSnapshot
  -> source-shaped SourceAssertion
    -> AssertionEvidence.source_assertion_id
      -> current operational Assertion
```

The raw snapshot and statement are immutable. `Assertion` remains the only
operational typed-fact projection. `Claim` and `FilmRelationship` are not new
write targets.

## Projection policy

- Only the latest successful snapshot for each Wikidata source object is
  eligible. A newer snapshot retracts older projected assertions; it never
  deletes evidence.
- Subject identity requires an exact source-object QID to canonical-entity QID
  match. That resolution is retained as an `EntityResolution`.
- Source properties are allow-listed in a pure policy. Unsupported properties,
  malformed values, and `novalue`/`somevalue` snaks are counted and skipped.
- Person-range credits create typed person targets from exact QIDs.
- `follows`, `followed_by`, `part_of_series`, and `based_on` remain
  `review_required` until the target kind satisfies the declared relationship
  vocabulary. A book is never silently shown as a film route.
- Context such as genre, language, country, company, award, location, runtime,
  budget, box office, and source identifiers is stored as a structured value
  when its target ontology is not yet a canonical entity family.
- Raw qualifiers, source rank, source revision, property ID, statement locator,
  and canonical URL are preserved.

The v1 allow-list contains 41 properties across credits, characters, explicit
work relationships, release/runtime/commercial values, production and
reception context, and external identity. Adding a property is a reviewed code
change, not an automatic passthrough.

## Scale shape

Projection uses keyset pages over source-assertion UUIDs and bulk target
resolution. It does not calculate film pairs and does not call a model or the
network. Database work therefore grows with retained statements rather than
quadratically with films. The command is safe to repeat after interruption.

At million-film scale, source acquisition and projection can be separate jobs;
the policy and evidence contract do not change. PostgreSQL remains sufficient
until measured traversal workloads justify a separate graph read model.

## Run and visualize

Raw data and generated reports remain local:

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/cinegraph \
PYTHONPATH=backend /Users/vkammela/opt/anaconda3/envs/cine-graph/bin/python \
  -m app.services.source_assertion_projection \
  --collection english-1000-retained-narrative-v1 \
  --batch-size 2000 \
  --report-dir data/evaluation/source-assertion-projection-v1
```

The command writes a small JSON audit and a self-contained dark HTML coverage
report. The key exit measures are:

- collection entities with any directly linked raw assertion;
- collection entities with at least one `resolved` or `published` assertion;
- created, reused, retracted, invalid, and unsupported statement counts; and
- the exact projector version and allow-list size.

Structured comparison synthesis may proceed only after the local report has
been reviewed. Semantic retrieval may suggest narrative evidence but cannot
fill a missing fact or change an assertion review state.
