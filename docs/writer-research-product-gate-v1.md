# CineGraph writer-research product gate (v1)

## Verdict

The evidence stack is useful infrastructure, not yet the product. CineGraph should become a **writer's film-study workbench**: ask a dramatic or craft question, inspect grounded examples and disagreements, then turn what was learned into an original design choice. A graph view, similar-film list, or confident-sounding answer is not a substitute for that loop.

## First-principles check

Assumptions to challenge:

- More films automatically make the tool more useful. They do not if a writer cannot find the right evidence or trust its provenance.
- A film pair is the natural starting point. Often the writer starts with a *problem* (for example, making a protagonist's betrayal feel earned) and does not know which films to compare.
- Similarity means a meaningful relationship. It may only reflect common vocabulary, genre, or cast.
- One authoritative interpretation exists. Reception and theme are often contested; a critic's reading must remain attributed.
- AI should generate a screenplay to demonstrate value. It can instead improve the human writer's options and judgment.

More fundamental requirements:

1. The user has an intention or unresolved decision, not just a title query.
2. The system must find evidence relevant to that intention, distinguish what happened in the film from an interpretation of it, and show where the evidence came from.
3. Useful comparison identifies *mechanism and difference*: what each film does, when it does it, and what experience or consequence follows. Metadata overlap alone cannot answer this.
4. The writer must retain agency. Suggestions are alternatives to accept, reject, or transform, not instructions to imitate.
5. A credible system must say when the available sources do not support a conclusion.

The minimum useful unit is therefore **one writer question, two contrasting film treatments, locatable evidence for each, one explicit uncertainty, and a user-owned note or decision**. This is a product test, not a claim that every question must force exactly two films.

## Rebuilt user journey

1. **Start with a question or intention.** Examples: “How can a villain expose the hero's ethics without winning?”; “What makes a return-to-power arc tragic rather than triumphant?”; “How do films make an AI relationship intimate or frightening?” The user may also start with a film.
2. **Discover a small, diverse study set.** Retrieve candidates by plot/craft/critical evidence, rerank for answerability and contrast, and show why each is suggested. Do not shortlist by embedding similarity alone.
3. **Study evidence in context.** Present a compact film map: premise and character situation, plot turning points, formal choices where sourced, reception/interpretation with named author, and a link to the source revision or article. Clearly label inferred structure as a candidate reading.
4. **Compare mechanisms, not labels.** Use “shared dramatic problem → different choices → different effects” cards. Separate objective fact, source interpretation, and CineGraph synthesis. Show counterexamples and missing evidence where relevant.
5. **Capture a creative move.** Let the writer save a note such as “keep the heir's claim legitimate but make the homecoming morally costly,” with the cited study evidence and their own alternate choice. The note is the user's work, not a canonical film fact.

The revised board offers initial question-first film leads and a browser-local
writer decision note (see [revision status](writer-study-revision-v1.md)).
It does not yet provide reliable synthesis or demonstrate that writers make
better choices with it.

## Data gate before expanding beyond 1,000

- Preserve exact source bytes and hashes in durable local storage. A database row pointing to a missing temporary file fails this gate. Reacquired revisions are new snapshots; old snapshot records and derivatives remain unchanged.
- For every film, audit identity/year/language and source attribution separately from narrative depth. Presence of a passage is not proof that it answers a writer's question.
- Index film-relevant passages by *evidence role* (plot event, character motivation, writing/development, formal craft, reception, theme/analysis, legacy) while retaining original section and source locator. Role labels are retrieval hints, not new facts.
- Collect criticism where access and reuse are permitted. Keep critical interpretations attributed, disagreement visible, and link-only records distinct from retained text. No unauthorized review scraping.
- Use films missing in writer tasks—not a fixed article quota—to prioritize additional sources and 2021–2025 titles.

## Product acceptance test

Create 20 fresh writer tasks across character change, moral dilemma, plot structure, worldbuilding, craft, genre inversion, reception disagreement, and unanswerable prompts. Include tasks that start with a film and tasks that start only with a dramatic problem. At least two independent writer/research reviewers should judge the *displayed result*, not top-ten retrieval recall, for: relevance, evidence accuracy, useful contrast, non-obviousness, uncertainty handling, and whether it produced a writer-owned next step. Record task time and first-use latency. An initial gate is at least 70% of tasks rated useful by both reviewers, zero unsupported factual claims in the tested output, and explicit abstention when source support is inadequate. Re-test with a new held-out set after changes.

This is intentionally not a promise that 70% is a production target; it is a decision threshold for the next iteration. A negative result means improve source coverage or retrieval/interaction before scaling the catalog.

## Research basis and limits

Kreminski and Martens identify unmet writing-support needs beyond getting unstuck: consistency, overall arc, reader experience, and expressive intent. Their paper includes film narrative in its scope, but it is not a user study of CineGraph; the workflow above is our design inference ([ACL 2022](https://aclanthology.org/2022.in2writing-1.11/)). MovieQA demonstrates that plot/story questions include why/how reasoning and that multiple text sources can matter; its benchmark does not validate our film-study UI ([MovieQA](https://arxiv.org/abs/1512.02902)). Recent research also finds creativity metrics disagree across domains, strengthening the case for human writer-task review rather than a single automated novelty score ([EACL 2026](https://aclanthology.org/2026.eacl-long.297/)).

Remaining assumptions: that cited film comparison changes writers' decisions; that two-film contrast is usually more useful than one deep film or a larger set; and that Wikipedia plus selectively licensed criticism supplies enough evidence for the chosen tasks. The 20-task study must test these rather than treating them as established truths.

## Local pilot checkpoint (2026-11-18)

The local Compose stack was rebuilt and migrated from `20261106_20` to
`20261107_23`; the API and web containers are healthy, and TMDb title search
returns attributed candidate results. This verifies the admin search surface,
not a complete movie-ingestion run. No new film was enqueued.

The working database contains 103,876 evidence chunks and 48,388 vectors, but
has **zero** `semantic_index_and_model_input` rights decisions. The serving
research collection has 1,000 memberships; the separate `writer-catalog-v1`
publication collection is not yet created. These aggregate vector counts do
not mean the user-facing corpus is eligible or ready. The live
Endgame × The Godfather query for family conflict while fighting injustice
returns `insufficient_evidence` before retrieval because neither film has an
approved snapshot. No retrieval score can be claimed for that current request.

The local story-generation setting is unset, and the configured secondary
generation port is unreachable from the API container. The local Ollama
inventory includes embedding models and a 15.7B coder model, but no selected,
evaluated small story-writing model. Thus the writer-facing generated brief is
not currently available.
Question-specific comparison guidance now echoes the writer's actual question
and avoids presuming a protagonist/risk structure; this is a presentation
correction, not a retrieval-quality gain.

The latest retained P05–P10 top-three source-support review found 7 of 12
film-side leads fully supported and 5 partially supported (one reviewer, six
development questions). That's 58% direct support in this small non-held-out
sample, not an 80% result and not the two-reviewer product gate above. The
current MVP gate remains open: source-specific rights review and publication,
a reproducible writer-catalog index, a selected local generator, and held-out
human-rated writer tasks are still required before MCP exposure.

### Local pilot follow-up (2026-11-18)

This supersedes the zero-rights-decision and pre-retrieval-abstention statements
above; those describe the earlier checkpoint, not the current local state.
Four exact English Wikipedia snapshots now have snapshot-scoped
`semantic_index_and_model_input` decisions: the indexed revisions of *The
Godfather* (1367608322) and *Avengers: Endgame* (1369169587), plus their newer
captured revisions. Only the two older, already indexed snapshots have
embeddings in the active research index. Decisions are local-pilot permissions
recorded after per-snapshot identity, revision, attribution and licence review;
they are not legal advice or commercial clearance. The newer snapshots have
not been chunked or indexed.

After approval of the indexed snapshots, the real API comparison for
*Avengers: Endgame* × *The Godfather* and “How do these follow conflicts
between family or close people when fighting injustice?” returned one paired
candidate lead rather than abstaining. The selected *Endgame* plot passage
covers Nebula/Gamora and the final battle; the selected *Godfather* plot
passage covers Connie's abuse, Sonny's revenge and Vito's response, then
Michael/Fredo. These excerpts are plausibly on-question and materially better
than the prior unrelated chunks, but this is one inspected development query,
not a blinded human label, pair-relevance score, or retrieval-quality estimate.
The UI still correctly calls it a lead needing review.

The selected generator gap remains open. The local 2.1 GB Qwen3-4B-Instruct
MLX checkpoint and its Python environment are present, but a direct runtime
check in this session fails because no Metal device is available. The actual
Mac Terminal is not exposed to this agent session, so host-side MLX inference
could not be checked. The local API reports `model_draft_available=false`;
no generator was started and no generated answer was verified. Prior saved 4B
generation trials contain character-attribution and citation-support errors;
they are not evidence that this feature is ready. The local health endpoint is
ready and reports 2,587 films; the active research collection reports 1,000
films, 74,053 narrative passages and 24,194 indexed chunks. The active
collection is still `english-1000-retained-narrative-v1`;
`writer-catalog-v1` has not been created/indexed. Free disk observed in this
session is about 4.9 GiB, below the documented 6 GiB indexing reserve. Do not
index the newer two snapshots or replace the active collection until a safe,
separate, reproducible writer-collection build is available.

Consequently this follow-up closes only the immediate two-film retrieval
diagnostic. It does not close the MVP gate: rights must be reviewed for each
source asset, the writer collection and end-to-end intake/index flow need
verification, generation must be run and evaluated rather than merely
configured, and the held-out two-reviewer writer-task gate remains unmeasured.
Do not expose the service as an MCP or describe the local pilot as production
ready on this evidence.
