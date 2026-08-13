# Research question catalog v1

## Purpose

CineGraph should help a writer investigate a film through many explicit lenses.
These are not a single score and they are not all facts of the same kind. Each
answer must declare its evidence class:

- **Source fact** — directly stated or structurally represented by a permitted
  source (for example, director, release date, sequel, or setting).
- **Structured derivation** — calculated from source facts using a named rule
  (for example, recurring editor across two films).
- **Narrative extraction** — a bounded observation extracted from a cited plot,
  production, or reception passage.
- **Editorial interpretation** — a human-reviewed reading of the source
  material. It must never be presented as an objective fact.
- **Semantic candidate** — a retrieval result to inspect, never proof of
  influence, similarity of intent, or plagiarism.

The catalog is deliberately broader than genre. A category is useful only when
it can lead to a question, an evidence trail, and a writer action.

## A. Work identity and form

These questions establish what is being researched and prevent false matches.

1. What is the canonical title, original title, aliases, and release year?
2. Which release events, territories, cuts, or versions are documented?
3. What is the original language, production country, runtime, and format?
4. Which genres and explicitly documented subjects or keywords apply?
5. Is this work part of a series, franchise, fictional universe, remake chain,
   adaptation chain, or other explicit work relationship?
6. What is the work's narrative form: feature, anthology, episodic work,
   documentary, animation, hybrid, or other documented form?

## B. Story engine and stakes

These are narrative-extraction questions. The answer must point to a plot or
synopsis passage and may be marked `uncertain` when the source is incomplete.

1. Who is the central viewpoint character or group?
2. What do they visibly want at the beginning?
3. What deeper need, fear, wound, belief, or contradiction is documented or
   reasonably extracted from the narrative?
4. What opposing force blocks the goal: person, institution, environment,
   technology, social order, internal conflict, fate, or time?
5. What is at stake if the protagonist fails: survival, identity, belonging,
   justice, freedom, family, civilization, species, knowledge, or another
   explicitly supported stake?
6. What is the inciting disruption or irreversible choice?
7. What escalating obstacles or pressure systems are described?
8. What reversal, revelation, or change in power is described?
9. What is the climax's decisive action or test?
10. What changes by the ending, and what remains unresolved?
11. Is the ending documented as hopeful, tragic, ambiguous, circular, ironic,
    or unresolved? Keep this as an interpretation unless the source explicitly
    describes it.

## C. Premise and thematic relation categories

These are reusable relation labels, not claims that two films mean the same
thing. A film may carry multiple labels, each with supporting passages.

### Threat and stakes

- apocalypse or post-apocalypse
- civilization collapse
- species extinction or survival
- environmental or ecological crisis
- pandemic, contagion, or biological threat
- war, occupation, or militarized conflict
- political repression or authoritarian control
- economic or class survival
- technological displacement or machine control
- existential or cosmic threat
- death, mortality, or afterlife
- home, exile, migration, or displacement

### Human and non-human relations

- human and artificial intelligence
- human and machine
- human and alien or other species
- creator and creation
- parent and child / family inheritance
- mentor and successor
- romance, loyalty, betrayal, or chosen family
- individual and community
- individual and institution
- human identity, memory, or embodiment
- language, translation, or communication barrier

### Agency and transformation

- coming of age
- return of the exiled or rightful heir
- redemption or moral recovery
- revenge and its cost
- sacrifice for another or for a collective
- quest for truth or forbidden knowledge
- identity concealment or revelation
- transformation, corruption, or recovery
- outsider assimilation or belonging
- rebellion against a system
- survival through adaptation
- impossible choice or competing loyalties

### World and speculative frame

- space exploration or space adventure
- first contact
- time travel or altered time
- alternate history or parallel worlds
- dystopia or utopia
- simulation, dream, or unreliable reality
- post-human or transhuman condition
- mythology, ritual, or supernatural order
- frontier, wilderness, or hostile environment
- enclosed-world or single-location pressure cooker
- journey, pilgrimage, or road structure
- historical memory or period transformation

### Social and moral inquiry

- justice and institutional failure
- law, punishment, or incarceration
- surveillance and privacy
- gender, race, caste, class, or colonial power
- family duty versus individual freedom
- science and ethics
- art, authorship, or performance
- truth versus comforting illusion
- progress versus preservation
- collective memory, erasure, or propaganda
- technology as liberation versus control

## D. Character and relationship questions

1. Which characters are allies, antagonists, foils, dependants, mentors, or
   successors according to the narrative evidence?
2. Which relationship changes most significantly from beginning to end?
3. What does each major relationship demand, conceal, exchange, or threaten?
4. Where does trust form, break, or become conditional?
5. Which character functions as a mirror or contrast to the protagonist?
6. Does the conflict move from personal to collective, or collective to
   personal?
7. Which character has agency at the climax, and what evidence supports that?

## E. Structure, time, and storytelling technique

1. Is the narrative linear, nonlinear, framed, episodic, cyclical, parallel,
   or multi-perspective?
2. Where does the source identify a flashback, flash-forward, framing device,
   unreliable account, or withheld information?
3. What information does the audience know before or after the protagonist?
4. Is the central mystery driven by identity, event, motive, world rules, or
   moral choice?
5. Which repeated image, object, location, phrase, or action is documented?
6. What formal device changes the viewer's interpretation of earlier events?
7. What is the dominant movement: investigation, pursuit, escape, siege,
   journey, transformation, trial, rescue, or return?

## F. Creative and production relations

These should initially be deterministic and source-backed.

1. Which director, writers, producers, editors, cinematographers, composers,
   designers, and principal performers are credited?
2. Which creative collaborators recur across another film in the catalog?
3. Is there a documented adaptation, remake, sequel, prequel, or source work?
4. Which production companies, distributors, or platforms recur?
5. Which awards, festivals, or reception milestones are documented?
6. Did the production use a documented technical or visual innovation?
7. What documented production constraint shaped the work: budget, location,
   schedule, censorship, effects method, or casting change?

## G. Cross-film investigation questions

These are answered only after selecting a typed relation or a clearly labeled
semantic candidate.

1. What exact relation connects the two works: installment, adaptation,
   shared person, shared company, shared setting, shared premise category,
   or narrative candidate?
2. Is the relation source fact, structured derivation, narrative extraction,
   editorial interpretation, or semantic candidate?
3. Which fields are shared, and which materially differ?
4. What changes in protagonist, stakes, antagonist, setting, or ending?
5. Does the later work inherit, invert, or abandon the earlier work's engine?
6. Is the comparison useful for premise, character, structure, world, tone,
   production, or research—and why?
7. What should a writer inspect next rather than copy?

## Evidence and quality rules

Every answer stores:

- `question_id` and catalog version;
- answer value plus `unknown`/`uncertain` state;
- evidence class;
- source snapshot, revision, URL, and passage/statement locator;
- extractor or derivation version;
- reviewer and status when interpretation is involved.

No answer is generated solely from a genre overlap. Embeddings may later rank
permitted narrative candidates for review; they cannot answer factual questions
or turn a thematic category into a claim of influence.

## Pilot acceptance gates

For the first 100 films:

1. Every film has a unique resolved Wikidata QID and English Wikipedia sitelink.
2. At least 95% have a title and release-year match verified against Wikidata.
3. Every published answer has a source locator or a deterministic formula.
4. Unknown fields remain explicitly unknown; they are not filled by a model.
5. At least five films are manually audited end-to-end, including *The
   Shawshank Redemption*, *Blade Runner*, *Her*, *Interstellar*, and *The Dark
   Knight* when present in the selected manifest.
6. Only after these checks pass do we run the same checkpointed process for the
   1,000-film shelf.

