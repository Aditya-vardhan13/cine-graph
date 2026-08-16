# Critical essays and perception layer — v1

## The first principle

A movie's production credits and plot establish some things that happened. An
essay, review or video essay explains what a person thinks those things mean.
Both are useful for a screenwriter, but they have different authority and
different reuse rights.

The platform therefore never turns criticism into an anonymous "fact" or
assumes an article page gives CineGraph the right to copy its text. Each work
has a named author, source URL, publication date, work-specific rights scope,
and an editorial review state. Each resulting claim is explicitly marked as an
interpretation, formal reading, historical context, reception judgement, or
comparative argument.

```text
source policy + exact work licence
  -> critical work (author, link, rights scope)
    -> attributed critical claim (CineGraph paraphrase + source locator)
      -> optional narrative/factual anchors and counterpoints
```

`critical_works` does not store a link-only article's body. A full-text record
is valid only when it points to an immutable `source_snapshot` whose licence
permits that use. `critical_claims.claim_text` is a concise editorial
paraphrase, not a copied passage; `source_claim_locator` directs a reader to
the original argument.

## What the Godfather example becomes

The Medium piece the team shared is a very good illustration of the layer we
want: it reads *The Godfather* through the American Dream, immigration,
family duty, informal power and the contrast between Vito and Michael's modes
of rule. Those are not canonical facts about the film. They are an author's
reading, useful precisely because it is named and contestable.

For that work CineGraph may store a link card such as:

| Field | Value |
| --- | --- |
| Work kind | Essay |
| Rights scope | `metadata_link_only` |
| Author | Zsoro |
| Lens | American Dream / power / family |
| Claim type | `interpretive_argument` |
| Visible wording | “The essay frames Vito and Michael as contrasting responses to immigrant aspiration, family obligation and modern power.” |
| Original | Link to the Medium article and a heading/paragraph locator |

It may **not** copy the full article, place it in an embedding index, or make
its interpretations appear as CineGraph's unqualified truth. Medium says its
writers retain rights while granting Medium a licence to run the service; that
does not license downstream reuse by us. [Medium Terms of
Service](https://help.medium.com/hc/en-us/articles/213481318-Medium-Terms-of-Service)

If the author gives permission or republishes under a compatible licence, the
same work can be upgraded to `permissioned` or `full_text_reusable`, with the
permission record and immutable snapshot retained.

## Vetted source registry

This registry is a source-policy starting point, **not** blanket permission to
scrape every page. Every individual work still needs a licence check and an
access-policy decision before content is requested.

| Source | Best role | Default CineGraph handling | Why |
| --- | --- | --- | --- |
| [Frames Cinema Journal](https://ojs.st-andrews.ac.uk/index.php/FCJ/about) | Peer-reviewed film/media scholarship | Review each work; eligible for `full_text_reusable` only with its explicit compatible licence | The journal states CC BY 4.0 unless otherwise noted, while authors retain copyright. |
| [OpenAlex](https://developers.openalex.org/api-reference/introduction) | Scholarly discovery metadata | `metadata_link_only` | Its metadata can find DOI, author and OA locations; it does not grant rights to a linked paper. |
| [Medium](https://help.medium.com/hc/en-us/articles/213481318-Medium-Terms-of-Service) | Independent criticism / creator essays | `metadata_link_only` | Author-retained rights; we preserve link and attribution, not body text. |
| [Film-Philosophy](https://journals.ed.ac.uk/f-p-submissions/policies) | Peer-reviewed theory and criticism | `review_required` | Current policy describes CC BY-NC; deployment use and the specific item must be checked. |
| [NECSUS](https://doaj.org/toc/2213-0217) | Film/media scholarship | `review_required` | DOAJ records show work-specific CC BY or CC BY-NC-ND licensing. |
| [Alphaville](https://openpolicyfinder.jisc.ac.uk/id/publication/37944) | Film/screen-media scholarship | `metadata_link_only` | Listed CC BY-NC-ND; no public reusable corpus by default. |
| [[in]Transition](https://mediacommons.org/intransition/about-intransition) | Peer-reviewed video essays | `review_required` | Works have supporting statements, but each work and any audiovisual material must be assessed independently. |

## Admission rules

1. Record source policy before acquisition: access route, terms, robots/API
   policy, rate limit, user agent, licence and review decision.
2. Capture only metadata for `metadata_link_only` work: title, author,
   publication date, canonical link, relevant films and tags. Do not retain
   text, images, transcripts or embeddings.
3. Capture full text only for `full_text_reusable` work after recording its
   explicit licence and a source revision/snapshot. Attribution must travel
   with every display and retrieval result.
4. Treat `permissioned` work as private to the stated permission terms; do not
   silently turn it into a public corpus.
5. Publish a critical claim only after editorial review. It must name its
   author/work and distinguish a factual anchor from the critic's conclusion.
6. A competing critical claim is not a data-quality failure. Store it as a
   separate attribution with a `counterpoint` anchor.

## Retrieval and embeddings

The retrieval index has two deliberately separate lanes:

- **Reusable evidence lane:** licensed, revisioned narrative passages and
  full-text criticism; retrieval can suggest candidates but cannot publish a
  relationship without review.
- **Discovery lane:** link-only work metadata, titles, author-supplied
  keywords and abstracts where separately licensed. It can recommend an essay
  to read but never indexes its body or synthesizes an unsupported claim.

This is why essays can make CineGraph genuinely insightful without making the
system a random-fact generator or a repository of copied criticism.

## Next small pilot

Start with 10 films that already have curated research answers. For each,
admit:

- one or two `Frames` works with individual CC BY confirmation;
- one independent/Medium-style link-only essay;
- one formal or videographic work if its text/asset rights are clear.

The acceptance test is not volume. It is whether a reader can distinguish in a
single screen: *what the film shows*, *what is historically documented*, *who
argues what it means*, and *which opposing reading is available*.

## Current admission result

The initial metadata-only manifest is
[`critical-pilot-manifest-v1.json`](critical-pilot-manifest-v1.json). It has
eight individually checked works covering all ten films from the existing
deep-research pilot:

| Film group | Work-level coverage | Admission state |
| --- | ---: | --- |
| *Batman Begins*, *The Dark Knight*, *The Dark Knight Rises* | 1 comparative CC BY article | Metadata/link only pending intentional source acquisition |
| *The Matrix* | 1 Film-Philosophy record | Link only; historic work licence must be checked |
| *Blade Runner*, *Mad Max: Fury Road*, *Get Out*, *Spider-Man: Into the Spider-Verse*, *Pulp Fiction* | 5 named works | Metadata/link only, despite compatible licence signals, until source snapshots exist |
| *2001: A Space Odyssey* | 1 CC BY-NC-ND cultural-criticism record | Link only by policy |

The manifest is imported without any article, image, transcript, or media
request:

```bash
PYTHONPATH=backend python -m app.services.critical_work_manifest \
  docs/critical-pilot-manifest-v1.json
```

It creates `critical_works` and film links only. A later full-text acquisition
command must be separate, pass a work-level licence/access review, and create
an immutable source snapshot before any record can change to
`full_text_reusable`.
