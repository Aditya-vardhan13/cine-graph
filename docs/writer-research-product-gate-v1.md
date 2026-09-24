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

The present comparison board is a starting surface for steps 3–4. It does not yet perform open-question film discovery, reliable synthesis, or step 5.

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
