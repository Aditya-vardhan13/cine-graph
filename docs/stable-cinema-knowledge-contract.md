# Stable cinema knowledge contract

**Status:** approved design target for Phase A before more product features.

## Why the current model must change

The first import proved two things:

1. a useful relation needs more than an overlap score; and
2. a Wikidata relationship target is not necessarily a film.

`based on` can point to a novel, play, comic, television work, or another film.
Storing it as an `ExternalWorkRelationship` with only a target QID loses the
target's type and label. Treating it as a film-to-film edge would produce false
screenwriting advice. Likewise, a recurring writer/director team is a
deterministic *derived* observation, not a source assertion.

The contract below separates those meanings permanently.

## Non-negotiable invariants

1. **Identity is independent of source and language.** One canonical entity can
   carry English, Telugu, Tamil, Hindi, and future aliases without merging
   editions or source rows.
2. **Imported statements are immutable evidence.** An importer creates a
   source assertion; it never silently rewrites a public fact.
3. **Every public fact has a path to evidence.** At minimum: subject identity,
   predicate, object/value, source record or statement URL, source revision,
   acquisition batch, and evidence class.
4. **Object type is mandatory for a relationship.** A link to a book must be
   shown as source material, never as a film connection.
5. **Derived and editorial insights are never source facts.** They have a
   formula or reviewer, version, and explicit evidence references.
6. **Vectors retrieve candidates only.** Similarity cannot become lineage,
   influence, a remake, or a commercial claim.
7. **The public API reads projections.** Raw evidence stays queryable and
   reproducible; UI-oriented cards can evolve without corrupting it.

## Minimal stable core

```text
source ──< ingestion_batch ──< source_record
                                  │
canonical_entity ──< entity_alias │ ──< assertion ──< assertion_evidence
       │                          │        │
       ├── film_profile (projection)       └── target_entity | typed value
       ├── person_profile (projection)
       └── work_profile (book / play / comic / episode / series / unknown)

insight_card ──< insight_evidence >── assertion | projected credit | narrative document
```

### `canonical_entity`

The durable identity node for **film, person, book, play, comic, television
work, game, organisation, or unknown work**. It has a stable UUID, an optional
Wikidata QID, entity kind, canonical label, lifecycle status, and no
source-specific interpretation.

`film_profile` remains a film-specific read model. It does not own the only
copy of identity and it is never used for a non-film target.

### `entity_alias`

An alias has text, normalized text, language/edition, script, alias kind
(`title`, `original_title`, `transliteration`, `credited_name`), source, and
status. This is the language-onboarding seam: adding Telugu does not require a
new title table or a special matching path.

### `source_record`

The immutable unit obtained from a source: its external ID, raw payload hash,
source revision, rights/access scope, and acquisition batch. The existing CMU
`CorpusRecord` and `NarrativeDocument` become compatible source-record and
licensed-document implementations; their text remains licence-separated.

### `assertion`

The only write target for imported facts and explicit relationships.

| Field | Meaning |
| --- | --- |
| `subject_entity_id` | Canonical subject |
| `predicate` / `source_property` | Normalized predicate and original source property, e.g. `follows` / `P155` |
| `object_entity_id` or typed value | Exactly one target: entity, date, number, text, or JSON qualifier value |
| `object_entity_kind` | Required whenever the target is an entity |
| `assertion_kind` | `source_fact`, `derived`, or `editorial` |
| `source_record_id`, `source_reference`, `batch_id` | Reproducible evidence path |
| `source_revision`, `qualifiers`, `rank` | Preserve source context rather than flatten it away |
| `review_status` | `raw`, `resolved`, `review_required`, `published`, or `retracted` |

An imported relationship is therefore an assertion whose target is a typed
entity. `based_on` can safely target a `book`; a UI query for film lineage
filters for a `film` target instead of guessing.

### Projections

`film_profile`, `film_credit`, `film_release_event`, and `film_genre` are
rebuildable read models. Each projection records its selection rule and the
assertion IDs used. Examples:

- display release date: *earliest known release event from published source
  assertions*;
- writer credit: published `writer` assertion from a specified source;
- film-to-film lineage: published relationship assertion whose target kind is
  `film`.

No importer directly mutates a projection field. A projector does so from
assertions, making a wrong source policy repairable by reprojecting rather than
rewriting history.

### `insight_card`

This is the product layer, not the fact layer. It stores:

- `kind`: `series_handoff`, `creative_engine`, `adaptation_route`,
  `release_context`, `narrative_candidate`, etc.;
- subjects and optional comparison target;
- writer question and concise explanation;
- `derivation_version` or editor/reviewer;
- status: `draft`, `review_required`, `published`, `retracted`;
- one or more evidence references.

Examples:

- **Series handoff:** a direct sequel edge plus the exact writer/director roles
  retained and changed between adjacent installments.
- **Creative engine:** at least two shared qualifying creative credits across
  two films; formula version is retained. It is labelled *derived from credits*.
- **Narrative candidate:** a permitted-document embedding neighbour, explicitly
  labelled *candidate for inspection*, never a claim of influence.

Do not materialize every possible pair of films. Pairwise combinations grow
quadratically. Calculate candidates on demand and persist only reviewed or
published cards.

## Relationship vocabulary and display rules

| Predicate family | Valid target kinds | Public label |
| --- | --- | --- |
| `follows`, `followed_by`, `part_of_series` | film, episode, series, unknown | `Installment lineage` only when target is a film; otherwise `Related work` |
| `based_on` | book, play, comic, film, series, game, unknown | `Source material`; use `Film adaptation` only for a film target |
| `remake_of`, `adaptation_of` | film, series, book, play, comic, game | Exact predicate, never inferred from title similarity |
| recurring creative credits | film + person | `Creative engine` and marked `derived` |
| embedding neighbour | film + licensed narrative document | `Narrative candidate`, never a fact |

Genre, release era, and cast overlap may be context filters. They are never
the headline relation or a percentage labelled as meaning.

## Migration sequence: additive, reversible, and observable

1. **Freeze the legacy tables as inputs.** Do not delete `FilmRelationship` or
   `ExternalWorkRelationship`; stop adding product semantics to them.
2. **Introduce schema migrations.** Add Alembic and establish a baseline for
   the existing PostgreSQL schema. New schema changes are migration-only;
   `create_all` remains development bootstrap only.
3. **Add the core tables additively.** Create `canonical_entity`,
   `entity_alias`, `source_record`, `assertion`, `assertion_evidence`, and
   `insight_card`/`insight_evidence`. No existing endpoint changes yet.
4. **Backfill with provenance.** Convert Films, People, CMU records, release
   events, credits, and legacy relationships. Each legacy `based_on` target is
   initially `unknown` until classified from Wikidata; it is not shown as a
   film link during backfill.
5. **Write a projector and parity tests.** Rebuild film read models from
   assertions in a shadow schema. Compare counts, QIDs, aliases, credits, and
   release events against the legacy catalogue. Fix selection policies before
   switching reads.
6. **Switch imports, then APIs.** Wikidata and every new-language adapter write
   source records/assertions first. Existing endpoints read projections;
   introduce `/films/{id}/lineage` and `/insights` before replacing Connection
   Lens.
7. **Publish only gated cards.** Start with 25 reviewed cards. Capture a
   feedback judgement: helpful, unhelpful, or misleading. A card type that
   fails this test does not scale.
8. **Retire legacy relationship reads only after parity.** Keep a reversible
   database migration and a documented reimport procedure.

## Phase gates

| Gate | Outcome that must be visible | Exit criterion |
| --- | --- | --- |
| A0: contract | Schema diagram, predicate vocabulary, migration baseline | no new endpoint relies on legacy relationship semantics |
| A1: evidence core | Backfilled typed assertions and target classification | 100% public relationship cards have evidence and target kind |
| A2: lineage | Film-to-film and source-material cards | no book/play/comic is displayed as a film relation |
| A3: creative engine | Derived collaboration cards | every card shows shared roles and derivation version |
| A4: narrative retrieval | Candidate cards from permitted text only | blind human evaluation beats genre-only baseline |
| B: language onboarding | Telugu pilot uses aliases/assertions/projections unchanged | no language-specific schema fork |

## Explicitly deferred

- A graph database: PostgreSQL plus indexed assertions is enough until measured
  traversals prove otherwise.
- A full generic ontology or automatic influence detection.
- A universal score for two films.
- Unlicensed scripts, subtitle corpora, or scraped commercial databases.

## Current import safety

The CMU archive remains a valid, licence-separated source layer. Current
Wikidata results are useful backfill input, but public lineage cards are not
expanded until relationship targets have a typed `canonical_entity` and the
new projection has passed parity checks.
