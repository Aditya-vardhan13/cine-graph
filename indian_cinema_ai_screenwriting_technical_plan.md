# Indian Cinema Intelligence + AI Screenwriting Platform

## 0. Project Status

**Working concept:** A computational Indian-cinema knowledge system combined with an AI-assisted screenplay development workspace.

**Primary goals**

1. Build a serious portfolio project demonstrating data engineering, entity resolution, graph modeling, NLP/LLM engineering, backend engineering, and product thinking.
2. Eventually turn the system into a B2B SaaS for writers, directors, production companies, film schools, or development teams.
3. Focus on Indian cinema rather than building a generic Hollywood-oriented screenplay copilot.
4. Make the hard part the structured representation and analysis of cinema, not merely an LLM API wrapper.

**Initial stack**

- Backend: Python
- API: FastAPI
- Database: PostgreSQL
- Vector search: pgvector initially
- Cache/queues: Redis, only when needed
- Object storage: S3-compatible storage, initially local filesystem or a cheap/free object-storage tier
- Processing: Python workers; add Spark only if corpus scale justifies it
- LLM: provider-agnostic abstraction
- Frontend: simple React/Next.js UI, or an equally lightweight frontend
- Deployment: Docker + a low-cost cloud deployment
- Observability: structured logs first; add tracing later

## Phase A data-contract decision (2026-08-12)

The first English-corpus import exposed a constraint that applies to every
future language edition: an explicit source relationship can target a book,
play, comic, series, or film, and a useful writer-facing observation can be a
derived result rather than a source fact. The platform therefore uses a stable
evidence core—canonical entities, source records, typed assertions, and
evidence-backed insight cards—with films, people, and language editions as
rebuildable projections.

This replaces the assumption that a relationship table can contain only two
films. The detailed schema contract, vocabulary, migration sequence, and phase
gates are in [Stable cinema knowledge contract](docs/stable-cinema-knowledge-contract.md).
All Phase A implementation work must follow that contract before adding more
connection UI or language-specific ingestion.

---

# 1. Product Thesis

Do **not** position the product as:

> "AI writes Indian screenplays."

Do not make the core experience:

> "Give me an idea and generate a 120-page screenplay."

That is easy to imitate and puts most of the value inside the LLM.

The stronger thesis is:

> **A cinematic intelligence system that helps writers develop, analyze, and write screenplays using structured knowledge derived from Indian cinema.**

The product combines:

```text
Indian cinema data
        ↓
entity resolution
        ↓
knowledge graph / relational graph
        ↓
narrative + screenplay analysis
        ↓
cinematic patterns
        ↓
AI writing/reasoning assistant
        ↓
writer's structured story
        ↓
screenplay
```

The LLM is a component of the system, not the system itself.

---

# 2. Why Indian Cinema

Indian cinema is not one homogeneous corpus.

The system should eventually cover:

- Hindi
- Tamil
- Telugu
- Malayalam
- Kannada
- Bengali
- Marathi
- Punjabi
- and additional regional industries as data becomes available

This creates interesting cross-industry questions:

- Which filmmakers have similar narrative fingerprints despite working in different languages?
- Which actors connect otherwise separate cinematic communities?
- Which narrative techniques spread between industries?
- Which films are structurally similar despite having no shared director, writer, or lead actor?
- How has screenplay structure changed across Indian cinema over decades?
- Which stylistic characteristics are actually associated with a filmmaker's corpus rather than a genre?
- How do regional industries differ in pacing, dialogue density, scene structure, songs, interval placement, etc.?

This is the main source of novelty.

---

# 3. Existing Research and Data

## 3.1 Indian Movie Database / TIMDB

The Indian Movie Database (TIMDB) is an open dataset covering Indian movies from roughly 1950-2019. It was designed as a structured Indian movie database and includes metadata useful for content-based analysis.

Source:
https://www.kaggle.com/datasets/pncnmnp/the-indian-movie-database

Reported fields include:

- title
- original title
- release date
- runtime
- genre
- IMDb rating/votes
- story
- summary
- tagline
- actors
- directors
- writers
- Wikipedia links

Use this as a **bootstrap metadata source**, not as the final authoritative database.

---

## 3.2 Indian Regional Movie Dataset

Academic dataset covering 2,851 movies across 18 Indian regional languages.

It contains metadata such as:

- genre
- language
- release year
- cast

Source:
https://arxiv.org/abs/1801.02203

This is useful for validating the regional coverage of our master film catalog.

---

## 3.3 Bollywood Movie Corpus

Academic corpus containing roughly 4,000 Bollywood movies from Wikipedia, covering approximately 1970-2017.

It includes:

- movie title
- cast
- plot
- co-reference information
- soundtrack information
- poster metadata
- cast relations
- cast centrality
- cast mentions

Source:
https://arxiv.org/abs/1710.04142

This is useful for plot and relationship experimentation.

---

## 3.4 Bollywood transcript dataset

IIT Bombay's IndicNLP page contains a Bollywood movie dataset with transcripts from 18 movies.

The data is segmented by:

```text
movie
  ↓
scene
  ↓
dialogue
```

The page states that the data is intended for non-commercial/research use.

Source:
https://www.cse.iitb.ac.in/~pjyothi/indiccorpora/nli.html

This is particularly useful for developing the screenplay parser and scene/dialogue representation before acquiring a larger corpus.

---

## 3.5 MovieSum

MovieSum is a non-Indian research dataset containing 2,200 movie screenplays paired with Wikipedia plot summaries.

The screenplays were manually formatted to preserve structural elements.

The dataset has approximately 34K tokens/words per screenplay on average and includes IMDb IDs.

The released representation uses XML and contains elements such as:

```xml
<script>
  <scene>
    <stage_direction>...</stage_direction>
    <scene_description>...</scene_description>
    ...
  </scene>
</script>
```

Sources:

https://arxiv.org/abs/2408.06281
https://huggingface.co/datasets/rohitsaxena/MovieSum

This is extremely useful for understanding how to represent screenplay structure computationally.

**Important:** Do not assume that MovieSum's raw screenplay text can be redistributed or used commercially just because it is downloadable. Verify the dataset's actual license and source rights before using it beyond research.

---

## 3.6 Wikidata

Wikidata provides a SPARQL query service that can be used to retrieve structured relationships.

Source:
https://www.wikidata.org/wiki/Help:SPARQL

Potential uses:

- film entities
- people
- directors
- writers
- actors
- countries
- languages
- release dates
- relationships between entities

Wikidata should be treated as a complementary structured source, not as the sole film database.

---

## 3.7 TMDB

TMDB offers an API, but its API terms contain important restrictions. In particular, the terms reserve rights around TMDB content and explicitly mention restrictions concerning machine learning/AI applications.

Source:
https://www.themoviedb.org/api-terms-of-use

Therefore:

**Do not build our commercial data strategy around blindly copying TMDB data into our database or training models on it.**

Use only after reviewing the current terms for the exact intended use.

---

# 4. Data Acquisition Strategy

The data should be separated into three major tiers.

## Tier 1: Film metadata

Do not start by scraping everything.

Bootstrap from:

- TIMDB
- Indian Regional Movie Dataset
- Bollywood Movie Corpus
- Wikidata
- appropriately licensed APIs/sources

Target for initial MVP:

```text
500-1,000 films
```

Eventually:

```text
10,000+ films
```

---

## Tier 2: Plot / synopsis / dialogue-level material

Potential sources:

- existing research datasets
- appropriately licensed plot data
- publicly available metadata
- subtitles/transcripts where licensing permits
- creator-contributed material

This provides:

- plot events
- characters
- themes
- dialogue
- narrative embeddings

Important distinction:

**Subtitle != screenplay**

A subtitle may provide dialogue but generally loses:

- scene headings
- action
- visual descriptions
- silence
- transitions
- screenplay formatting
- explicit character/action annotations

Therefore subtitles should be modeled separately.

---

## Tier 3: Actual screenplays

This is the highest-value and hardest dataset.

Potential sources:

- filmmaker/writer-published scripts
- publisher/licensed screenplay books
- publicly released scripts
- Film Companion and similar legitimate publications
- creator-contributed scripts
- academic/open research datasets where license permits
- individually licensed scripts

There is no known comprehensive public corpus of Indian screenplays comparable to what we need.

Therefore **proper acquisition work is required**.

Do not build the product around indiscriminate scraping of copyrighted screenplay repositories.

Target initial corpus:

```text
50-100 high-quality screenplays
```

Target research corpus:

```text
300-1,000+ screenplays
```

The quality and diversity of the corpus matter more than raw count.

---

# 5. Data Provenance Is a First-Class Requirement

Every acquired document should record provenance.

Suggested fields:

```text
source_id
source_url
source_name
source_type
license
rights_status
acquisition_date
language
film_id
document_hash
```

Example:

```json
{
  "film_id": "film_18273",
  "source_name": "Creator-published",
  "source_url": "...",
  "source_type": "screenplay",
  "rights_status": "licensed",
  "acquisition_date": "2026-08-12",
  "language": "Tamil"
}
```

Maintain a distinction between:

```text
raw copyrighted material
        !=
derived analytical features
        !=
publicly redistributable data
```

The eventual SaaS should not require redistributing the raw screenplay corpus.

---

# 6. Long-Term Data Flywheel

A strong long-term strategy is creator-contributed scripts.

Writer uploads a screenplay:

```text
screenplay
    ↓
parser
    ↓
story graph
    ↓
analysis
    ↓
writer receives value
```

With appropriate consent and privacy controls, the platform could aggregate **derived/anonymized structural statistics** rather than raw screenplay text.

Potential flywheel:

```text
public / licensed cinema corpus
             +
creator-contributed scripts
             ↓
cinematic intelligence
             ↓
better writer assistance
             ↓
more writers
             ↓
more opt-in data
```

This is strategically healthier than depending entirely on web scraping.

---

# 7. Traditional Screenwriting Workflow

Screenwriting is not simply "write scenes."

A practical development pipeline is:

```text
IDEA
 ↓
LOGLINE
 ↓
PREMISE / THEME
 ↓
CHARACTERS
 ↓
SYNOPSIS
 ↓
TREATMENT
 ↓
BEAT SHEET / STRUCTURE
 ↓
SEQUENCE OUTLINE
 ↓
SCENE OUTLINE
 ↓
SCREENPLAY
 ↓
TABLE READ / FEEDBACK
 ↓
REWRITE
 ↓
REWRITE
 ↓
PRODUCTION SCRIPT
```

Different writers use different processes, so the application must not force one methodology.

The key insight:

**These are different resolutions of the same story.**

```text
Idea
 ↓
Logline
 ↓
Story
 ↓
Treatment
 ↓
Beats
 ↓
Scenes
 ↓
Screenplay
```

The product should maintain consistency across these representations.

---

# 8. Screenplay as Structured Data

A screenplay looks like prose, but semantically it is semi-structured.

Example:

```text
INT. HOTEL ROOM - NIGHT

Rahul enters.

Maya is sitting on the bed.

                    MAYA
              You came.

Rahul puts a gun on the table.
```

Machine representation:

```text
Scene
 ├── Location: Hotel Room
 ├── Time: Night
 ├── Characters:
 │   ├── Rahul
 │   └── Maya
 ├── Actions:
 │   ├── Rahul enters
 │   └── Rahul puts gun on table
 ├── Dialogue:
 │   └── Maya -> "You came."
 ├── Prop:
 │   └── Gun
 └── Narrative state change:
     └── Gun is now known/present
```

This structured representation is central to the entire project.

---

# 9. Proposed Story Schema

Do not make the LLM's prompt the source of truth.

Create a canonical story representation.

## Project

```text
Project
 ├── id
 ├── title
 ├── language
 ├── genre
 ├── logline
 ├── premise
 ├── theme
 ├── story
 └── version
```

## Character

```text
Character
 ├── id
 ├── name
 ├── age
 ├── role
 ├── wants
 ├── needs
 ├── fears
 ├── traits
 ├── relationships
 ├── arc
 └── knowledge_state
```

## Scene

```text
Scene
 ├── id
 ├── sequence_number
 ├── heading
 ├── location
 ├── time
 ├── characters
 ├── objective
 ├── conflict
 ├── action
 ├── dialogue
 ├── emotional_start
 ├── emotional_end
 ├── revelations
 ├── setups
 ├── payoffs
 ├── narrative_function
 ├── preceding_scene
 └── following_scene
```

## Event

```text
Event
 ├── id
 ├── type
 ├── actor
 ├── target
 ├── location
 ├── time
 ├── cause
 └── consequences
```

## Relationship

Examples:

```text
Character -> knows -> Character
Character -> loves -> Character
Character -> hates -> Character
Character -> suspects -> Character
Character -> owes -> Character

Scene -> causes -> Scene
Scene -> reveals -> CharacterFact
Scene -> sets_up -> Event
Scene -> pays_off -> Setup
```

---

# 10. Story Graph

The canonical story should form a graph.

```text
                       STORY
                         |
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
     CHARACTERS         PLOT          THEMES
          |              |              |
          ↓              ↓              ↓
    RELATIONSHIPS      EVENTS         MOTIFS
          |              |
          └───────┬──────┘
                  ↓
                SCENES
                  |
          ┌───────┼────────┐
          ↓       ↓        ↓
       PEOPLE   PLACE    EVENTS
```

The graph does not necessarily require Neo4j initially.

Use PostgreSQL as the source of truth and model relationships with relational tables.

Add a graph database only if actual workloads justify it.

---

# 11. Narrative Representation

Do not hard-code one screenplay theory.

Possible frameworks include:

- Three-act structure
- Five-act structure
- Hero's Journey
- Save the Cat
- Eight-sequence structure
- Story Circle
- custom writer-defined structures

Instead, model narrative mechanics directly.

For each scene:

```text
narrative_function
character_function
conflict_type
information_change
emotional_movement
causal_parent
consequences
pacing
```

Frameworks can then be mapped onto the underlying representation.

Example:

```text
Scene 21
    narrative_function = escalation

Save the Cat:
    Midpoint

Hero's Journey:
    Ordeal

Custom framework:
    Major reversal
```

This keeps the system flexible.

---

# 12. Indian-Specific Narrative Features

Indian cinema should not simply be treated as Hollywood screenwriting with Indian actors.

Potential domain-specific entities/features:

```text
song
dance sequence
montage
interval point
comedy track
mass/elevation sequence
emotional sequence
visual spectacle
family conflict
regional setting
language switch
code-switching
```

A song may simultaneously:

```text
advance romance
+
reveal character
+
compress time
+
establish geography
+
reinforce theme
```

The system should therefore allow one scene/sequence to have multiple narrative functions.

---

# 13. Cinematic DNA

Every film can receive a measurable feature vector.

Possible features:

```text
dialogue_density
action_density
average_scene_length
scene_length_distribution
dialogue_action_ratio
character_density
character_interaction_density
flashback_frequency
nonlinear_story_frequency
narration_frequency
monologue_frequency
interruption_frequency
question_frequency
location_transition_frequency
silence_proxy
song_frequency
montage_frequency
interval_position
revelation_frequency
```

Example:

```text
Film DNA

Dialogue density          0.91
Non-linearity             0.71
Scene fragmentation       0.88
Character density         0.51
Narration                 0.31
Social commentary         0.87
Romance                   0.72
```

These should initially be measurable statistics rather than LLM-generated "vibes."

---

# 14. Style Model

Do not begin with:

> "Write like Director X."

Instead:

```text
Director corpus
      ↓
feature distributions
      ↓
stylistic fingerprint
```

Then compare a user's screenplay against that fingerprint.

Example:

```text
User screenplay vs Director X

Dialogue density       +18%
Scene length            -12%
Interruptions           +31%
Nonlinear transitions   +7%
Monologues              -22%
```

The product can explain *why* something is similar instead of pretending style is a single embedding.

---

# 15. Similarity Engine

Represent films, scenes, sequences, and scripts using multiple representations.

### Structured features

```text
X_structured
```

### Semantic embeddings

```text
X_embedding
```

### Graph features

```text
X_graph
```

Potential composite similarity:

```text
similarity =
    α * structured_similarity
  + β * semantic_similarity
  + γ * graph_similarity
```

Start with simple weighted combinations.

Do not build a complicated learned model until we have evaluation data.

---

# 16. The AI Application

The writer should have several AI modes.

## Explore

User:

> Give me possible directions.

AI:

```text
Option A
Option B
Option C
```

Does not modify canonical story state.

---

## Challenge

User:

> Try to break my story.

System checks:

```text
plot holes
weak motivations
causality gaps
character inconsistencies
pacing problems
unresolved setups
weak stakes
knowledge-state violations
```

This should be one of the strongest features.

---

## Develop

User:

> Turn this beat into five possible scenes.

AI proposes alternatives.

Writer chooses one.

---

## Write

User:

> Write Scene 17.

AI uses:

```text
story state
character state
scene objective
previous scenes
future constraints
style preferences
```

to generate the scene.

---

## Analyze

User:

> What's wrong with Act 2?

The system produces evidence-backed analysis.

---

# 17. Killer Feature: Consequence Analysis

This should be a major design target.

Suppose the writer changes:

```text
Scene 12:
Maya does NOT tell Rahul the truth.
```

The system should identify downstream effects:

```text
Scene 17
Maya knowledge state changes

Scene 24
Rahul motivation becomes inconsistent

Scene 31
Current reveal depends on information
Maya should not have

Scene 38
Climax setup may no longer be valid
```

This is essentially:

> **dependency management for stories**

The system maintains causality and character knowledge across the screenplay.

That is much more defensible than generic text generation.

---

# 18. AI Architecture

Avoid:

```text
user prompt
    ↓
LLM
    ↓
answer
```

Use:

```text
                 USER
                   |
                   ↓
             FastAPI API
                   |
             Intent Router
                   |
       ┌───────────┼────────────┐
       ↓           ↓            ↓
 Story Engine   Retrieval    Analysis
       |           |            |
       └───────────┼────────────┘
                   ↓
              Context Builder
                   |
                   ↓
                 LLM
                   |
          ┌────────┴────────┐
          ↓                 ↓
     Draft output      Structured output
          |                 |
          └────────┬────────┘
                   ↓
          Consistency Checker
                   |
                   ↓
            Story Graph update
```

LLM output should be structured wherever possible.

Use JSON schemas / Pydantic models for machine-readable operations.

---

# 19. RAG Strategy

The system needs multiple retrieval types.

### Story retrieval

Retrieve:

- relevant scenes
- character facts
- prior events
- unresolved setups
- future constraints

### Cinema retrieval

Retrieve:

- similar films
- similar scenes
- similar narrative patterns
- genre patterns
- filmmaker fingerprints

### Semantic retrieval

Use embeddings for:

- scene similarity
- theme similarity
- dialogue similarity
- plot similarity

### Structured retrieval

Use SQL for:

- relationships
- dates
- film metadata
- character knowledge
- scene ordering
- causal relationships

Do not put everything into a vector database.

---

# 20. Database Architecture

Start with PostgreSQL.

Suggested high-level schema:

```text
users
projects
project_versions

characters
character_relationships

scenes
scene_characters
scene_events

locations
props
themes
motifs

story_events
story_relationships

films
people
film_people
film_relationships
film_genres
film_languages

screenplay_documents
screenplay_scenes

analysis_results

embeddings
data_sources
```

Use PostgreSQL + pgvector initially.

Potentially add:

```text
Redis
```

for:

- caching
- job queues
- rate limiting

Potentially add:

```text
Neo4j
```

later if graph traversal becomes a dominant workload.

---

# 21. Raw Data Storage

Do not store large raw documents directly in PostgreSQL.

Use:

```text
Object Storage
   |
   ├── raw/
   ├── normalized/
   ├── parsed/
   └── derived/
```

For local development:

```text
data/
  raw/
  normalized/
  parsed/
  derived/
```

For production:

S3-compatible object storage.

Each document should have a database metadata record.

---

# 22. Processing Pipeline

```text
             RAW SOURCE
                  ↓
             downloader
                  ↓
             provenance
                  ↓
          document normalization
                  ↓
          language detection
                  ↓
          OCR if necessary
                  ↓
        screenplay classification
                  ↓
          screenplay parser
                  ↓
          scene segmentation
                  ↓
       character/entity extraction
                  ↓
          event extraction
                  ↓
        relationship extraction
                  ↓
          feature extraction
                  ↓
             embeddings
                  ↓
            Story Graph
```

Each step should be independently rerunnable.

Do not create one giant script.

---

# 23. Recommended Python Project Structure

```text
cinegraph/
│
├── app/
│   ├── main.py
│   │
│   ├── api/
│   │   ├── projects.py
│   │   ├── scripts.py
│   │   ├── scenes.py
│   │   ├── characters.py
│   │   ├── analysis.py
│   │   └── chat.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   └── security.py
│   │
│   ├── models/
│   │   ├── project.py
│   │   ├── screenplay.py
│   │   ├── scene.py
│   │   ├── character.py
│   │   └── film.py
│   │
│   ├── schemas/
│   │   ├── project.py
│   │   ├── screenplay.py
│   │   ├── scene.py
│   │   └── analysis.py
│   │
│   ├── services/
│   │   ├── screenplay_parser.py
│   │   ├── entity_resolution.py
│   │   ├── story_engine.py
│   │   ├── retrieval.py
│   │   ├── embeddings.py
│   │   ├── analysis.py
│   │   └── llm.py
│   │
│   ├── db/
│   │   ├── session.py
│   │   └── repositories/
│   │
│   └── workers/
│       ├── ingestion.py
│       ├── parsing.py
│       └── analysis.py
│
├── data/
│   ├── raw/
│   ├── normalized/
│   ├── parsed/
│   └── derived/
│
├── scripts/
│   ├── ingest_timdb.py
│   ├── ingest_wikidata.py
│   ├── parse_screenplays.py
│   └── build_embeddings.py
│
├── tests/
│
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

---

# 24. FastAPI API Design

Initial endpoints:

```text
POST /projects
GET  /projects/{project_id}

POST /projects/{project_id}/characters
GET  /projects/{project_id}/characters

POST /projects/{project_id}/scenes
GET  /projects/{project_id}/scenes

POST /projects/{project_id}/analyze
POST /projects/{project_id}/chat

POST /screenplays/upload
GET  /screenplays/{id}

GET /films/{id}
GET /films/{id}/similar
GET /films/{id}/graph

GET /characters/{id}/relationships
```

AI operations should be explicit.

Example:

```text
POST /projects/{id}/ai/explore
POST /projects/{id}/ai/challenge
POST /projects/{id}/ai/develop
POST /projects/{id}/ai/write
POST /projects/{id}/ai/analyze
POST /projects/{id}/ai/consequences
```

---

# 25. LLM Tool Interface

The LLM should have tools such as:

```text
get_project_state()
get_character(character_id)
get_scene(scene_id)
get_previous_scenes(...)
get_future_constraints(...)
search_similar_films(...)
search_similar_scenes(...)
get_director_style(...)
find_unresolved_setups(...)
find_character_knowledge(...)
simulate_change(...)
```

The LLM should not directly query arbitrary database tables.

Give it controlled tools.

---

# 26. Frontend MVP

Do not overbuild the UI.

Three main views are enough initially.

## View 1: Story Board

```text
Project
 |
 ├── Logline
 ├── Theme
 ├── Characters
 ├── Beats
 └── Sequences
```

Drag/drop cards can come later.

## View 2: Screenplay Editor

Simple screenplay editor:

```text
Scene heading

Action

CHARACTER
Dialogue

Action
```

The editor should support standard screenplay elements.

## View 3: AI / Analysis panel

Right side:

```text
AI

[ Explore ]
[ Challenge ]
[ Develop ]
[ Write ]

Analysis
---------
Scene purpose
Character consistency
Pacing
Open threads
Related Indian films
```

That is enough for MVP.

---

# 27. Indian Cinema Explorer

This can be a second major UI.

Example:

```text
                 INDIAN CINEMA

Film: X

Director
Writer
Actors
Language
Year

Similar Films
-------------------
Film A  87%
Film B  84%
Film C  81%

Narrative DNA
-------------------
Dialogue        0.81
Nonlinear       0.72
Action          0.64
Romance         0.37
...

Connections
-------------------
Director → Film
Actor → Film
Writer → Film
Remake → Film
```

This demonstrates the data/graph side of the project.

---

# 28. First MVP

Do NOT start with 10,000 films and a giant UI.

### MVP-0: Data proof

Target:

```text
500-1,000 films
50-100 screenplay/transcript documents
```

Build:

- canonical film schema
- person schema
- entity resolution
- film-person graph
- basic screenplay parser
- scene segmentation
- basic feature extraction

Success criterion:

> We can reliably transform raw cinema documents into structured entities and relationships.

---

### MVP-1: Cinema intelligence

Build:

- film similarity
- scene similarity
- director fingerprint
- narrative feature vectors
- relationship explorer
- temporal analysis

Success criterion:

> The system discovers interesting relationships that are not explicitly stored in the raw source.

---

### MVP-2: Writer workspace

Build:

- project
- characters
- beats
- scenes
- screenplay editor
- story graph

Success criterion:

> A writer can develop a short film from premise to structured screenplay.

---

### MVP-3: AI collaborator

Build:

- Explore
- Challenge
- Develop
- Write
- Analyze
- Consequence analysis

Success criterion:

> AI can modify/develop the story while preserving consistency.

---

# 29. First Technical Experiment

Before building the SaaS, run one narrow experiment.

Take:

```text
20-50 screenplays/transcripts
```

Parse them into:

```text
movie
scene
character
dialogue
action
location
time
```

Then compute:

```text
scene_length
dialogue_density
character_count
speaker_count
location_count
dialogue_action_ratio
scene_transition_rate
```

Cluster the films.

Then inspect:

> Are the clusters actually meaningful?

If yes, add richer features.

If not, change the representation before building the product.

This is the fastest way to validate the core hypothesis.

---

# 30. Entity Resolution

This will likely become one of the hardest and most valuable components.

Examples:

```text
A. R. Rahman
A.R. Rahman
A R Rahman
Allah Rakha Rahman
A.R.Rahman
```

All should resolve to one entity.

Similarly:

```text
மணிரத்னம்
Mani Ratnam
Mani Rathnam
Maniratnam
```

Potential pipeline:

```text
normalization
      ↓
exact match
      ↓
string similarity
      ↓
phonetic similarity
      ↓
metadata agreement
      ↓
embedding similarity
      ↓
candidate generation
      ↓
confidence score
      ↓
human verification
```

Do not use an LLM for every entity-resolution decision.

Use deterministic/high-recall candidate generation first.

---

# 31. Evaluation

The system needs measurable evaluation.

## Entity resolution

Metrics:

```text
precision
recall
F1
false merge rate
false split rate
```

## Scene parsing

Create a manually labeled test set.

Measure:

```text
scene segmentation F1
character extraction F1
dialogue attribution accuracy
location extraction accuracy
```

## Similarity

Human evaluation:

```text
Does Film A actually resemble Film B?
```

Compare:

```text
metadata similarity
semantic similarity
structured similarity
combined similarity
```

## AI story consistency

Create deliberate changes and test:

```text
Does the system identify downstream contradictions?
```

This can become a very strong technical section in the README.

---

# 32. What Not To Build Yet

Avoid these initially:

- multi-agent "AI writers"
- autonomous screenplay generation
- fine-tuning a large model
- custom LLM training
- Neo4j unless required
- Kafka unless required
- Kubernetes
- real-time collaboration
- mobile app
- production scheduling
- budgeting
- full studio management
- automatic video generation
- voice cloning

They add complexity without validating the core hypothesis.

---

# 33. Cost Strategy

You said you are willing to spend some money, but free tiers are preferable.

Recommended approach:

### Development

Run locally:

```text
PostgreSQL
pgvector
Redis
FastAPI
frontend
```

using Docker Compose.

Cost:

```text
~$0
```

apart from LLM/API usage.

### Production prototype

Use:

```text
managed PostgreSQL
object storage
cheap container host
```

Start with free/low-cost tiers where available.

Do not architect around a vendor's free tier. Treat free tiers as development conveniences.

### LLM

Use a provider abstraction:

```python
class LLMProvider:
    async def generate(...)
    async def structured(...)
    async def embed(...)
```

Then providers can be swapped.

For development:

- cheap/small models for extraction
- stronger model only for complex reasoning
- cache deterministic analysis
- batch embedding operations

Do not send an entire screenplay to an expensive model for every request.

---

# 34. Data/LLM Cost Optimization

For a 120-page screenplay, do not use:

```text
whole screenplay → LLM → answer
```

Instead:

```text
screenplay
   ↓
structured parse
   ↓
scene chunks
   ↓
embeddings
   ↓
retrieval
   ↓
small relevant context
   ↓
LLM
```

For analysis:

```text
cheap model / deterministic parser
        ↓
structured features
        ↓
strong LLM only for interpretation
```

This makes the system much cheaper.

---

# 35. Security and Privacy

Because users may upload unpublished scripts, treat screenplay content as sensitive.

Requirements:

- project-level authorization
- encrypted transport
- encrypted object storage
- signed object URLs
- no accidental public URLs
- deletion support
- audit logs
- clear data retention policy
- provider-specific controls around LLM data retention
- never use private user scripts for training without explicit consent

For SaaS, this is not optional.

---

# 36. Product Differentiation

Existing screenwriting tools already cover much of:

- formatting
- outlining
- collaboration
- production breakdown
- basic AI assistance

Examples include Final Draft, Celtx, WriterDuet, Arc Studio, Fade In and others. The current landscape is crowded. See:
https://blog.celtx.com/best-screenwriting-softwares/

Indian screenwriters also discuss tools such as Scrite, Celtx, WriterDuet, Fade In and StudioBinder, and there are emerging Indian-specific tools exploring Indian-language support and AI-assisted prewriting.

Therefore our differentiation should be:

```text
traditional screenwriting editor
                +
Indian cinema knowledge graph
                +
narrative analysis
                +
story-state reasoning
                +
consequence analysis
```

Not simply:

```text
screenwriting editor + ChatGPT
```

---

# 37. Core Product Loop

The ideal experience:

```text
                 WRITER
                    ↓
               Story idea
                    ↓
              Story Graph
                    ↓
              AI reasoning
                    ↓
          Indian cinema retrieval
                    ↓
            Writer chooses
                    ↓
             Scene development
                    ↓
              Screenplay
                    ↓
          Consistency analysis
                    ↓
             Revision
                    ↓
              Better story
```

The AI should continuously reason over the structured story state.

---

# 38. Long-Term Vision

Eventually:

```text
                 INDIAN CINEMA GRAPH
                         |
       ┌─────────────────┼─────────────────┐
       ↓                 ↓                 ↓
   FILMS             PEOPLE            PATTERNS
       |                 |                 |
       └─────────────────┼─────────────────┘
                         ↓
                 CINEMATIC INTELLIGENCE
                         |
              ┌──────────┴──────────┐
              ↓                     ↓
        CINEMA EXPLORER       WRITER WORKSPACE
                                    |
                         ┌──────────┼───────────┐
                         ↓          ↓           ↓
                      Explore    Develop      Write
                         ↓          ↓           ↓
                      Challenge  Analyze   Consequences
```

Potential B2B customers:

- screenwriters
- directors
- production companies
- development executives
- film schools
- writers' rooms
- OTT content teams
- research/film studies organizations

---

# 39. Immediate Execution Plan

## Weekend 1

### Day 1

Set up:

```text
FastAPI
PostgreSQL
pgvector
Docker
basic React frontend
Alembic
pytest
```

Create initial schemas:

```text
films
people
film_people
genres
languages
data_sources
```

### Day 2

Ingest TIMDB / another appropriately usable metadata dataset.

Build:

```text
normalization
deduplication
entity IDs
```

Create queries:

```text
films by director
actors shared between films
writers shared between films
films by language
films by decade
```

### Day 3

Build the first cinema explorer.

No AI yet.

Show:

```text
film
people
relationships
similar films
```

---

# 40. Weekend 2

Take a small screenplay/transcript corpus.

Build:

```text
Document
 ↓
Parser
 ↓
Scene
 ↓
Dialogue
 ↓
Character
 ↓
Location
```

Create:

```text
screenplay_scenes
scene_characters
dialogues
```

Then calculate:

```text
scene length
dialogue density
character density
speaker distribution
location distribution
```

---

# 41. Weekend 3

Build the first analytical engine.

Implement:

```text
film fingerprint
scene fingerprint
similarity search
director fingerprint
```

Use:

```text
structured features
+
embeddings
```

Create the first interesting query:

> Find Indian films that are structurally similar but do not share a director, writer, or lead actor.

If the output is interesting, we have validated a major part of the idea.

---

# 42. Weekend 4

Start the writer workspace.

Implement:

```text
Project
Characters
Story
Beats
Scenes
Screenplay
```

Add a simple editor.

Then add one AI feature:

> **Challenge my story.**

This is preferable to generation because it immediately tests whether the structured story representation is useful.

---

# 43. First AI Prompting Principle

Never give the LLM only:

```text
Here is my screenplay.
Analyze it.
```

Give it structured context:

```text
PROJECT
  premise
  theme
  genre

CHARACTERS
  objectives
  relationships
  arcs
  knowledge

CURRENT SCENE
  objective
  conflict
  events

PREVIOUS EVENTS
  relevant causal chain

UNRESOLVED THREADS
  setups

FUTURE CONSTRAINTS
  known planned events

CINEMA REFERENCES
  relevant structural patterns
```

Then ask for a structured response.

---

# 44. The First "Wow" Demo

The first public demo should ideally look like this:

User enters:

> "A police officer investigates a murder committed in his own family."

System builds:

```text
Premise
Characters
Relationships
Potential conflicts
```

Writer develops 20 scenes.

Then asks:

> "Challenge my story."

System says:

```text
Problem 1
Scene 14 reveals information that the protagonist
already knew in Scene 8.

Problem 2
The antagonist's action in Scene 21 has no causal
connection to the preceding decision.

Problem 3
The protagonist's motivation changes between
Scenes 16 and 23 without an intervening event.

Problem 4
The setup introduced in Scene 7 has no payoff.
```

Then:

> "Show me Indian films with similar structural patterns."

System returns:

```text
Film A
Structural similarity: 82%

Why:
+ similar investigation structure
+ family-conflict subplot
+ midpoint revelation
- different climax mechanism
```

Then:

> "Give me three ways to fix Problem 2."

AI proposes options.

Writer selects one.

The story graph updates.

That is the product demo I would aim for.

---

# 45. Definition of Done for the First Serious Version

The first version is successful if it can:

- ingest Indian film metadata
- resolve duplicate people/films
- maintain film-person relationships
- ingest a screenplay/transcript
- parse scenes
- identify characters
- construct a story graph
- calculate basic cinematic fingerprints
- retrieve similar films/scenes
- create a writer project
- represent characters/scenes/beats
- let an LLM reason over the story graph
- detect at least some continuity/causality issues
- explain why a retrieved film/scene is similar
- generate a scene using structured story context
- preserve story state after edits

It does **not** need:

- 50,000 films
- thousands of screenplays
- perfect AI writing
- a beautiful UI
- autonomous agents
- a production-ready SaaS billing system

---

# 46. Current Research Conclusions

The most important conclusions from the research so far:

1. **There is enough existing metadata to bootstrap without immediately scraping the entire web.**
2. **There is no obvious comprehensive, clean, legally reusable Indian screenplay corpus.**
3. **Screenplay acquisition will therefore be a real project component.**
4. **Existing screenplay research datasets such as MovieSum provide useful representation/parsing ideas.**
5. **Indian regional cinema datasets prove that cross-language structured metadata is feasible.**
6. **Subtitles/transcripts can supplement screenplay data but must not be treated as equivalent.**
7. **Screenplay software is already a mature category, so formatting alone is not differentiation.**
8. **The strongest differentiation is the combination of Indian cinema intelligence + structured story representation + LLM reasoning.**
9. **The story graph should be the canonical representation, not the LLM context window.**
10. **Consequence analysis and continuity reasoning are promising core features.**
11. **The initial product should be writer-assistance, not autonomous screenplay generation.**
12. **Data provenance and rights must be tracked from the beginning because the long-term goal is SaaS.**

---

# 47. Immediate Next Research Task

Before implementation goes deep, conduct a **source-by-source Indian cinema data audit**.

Create a spreadsheet/table containing:

```text
Source
Type
Languages
Approx. films
Approx. scripts
Metadata
Plot
Dialogue
Full screenplay
License
Commercial use
API
Scraping allowed?
Quality
Coverage
```

Sources to audit first:

```text
TIMDB
Wikidata
Indian Regional Movie Dataset
Bollywood Movie Corpus
IIT Bombay Bollywood transcripts
MovieSum
Film Companion
WritersRoom
publisher/creator screenplay releases
legitimate screenplay archives
subtitle sources
TMDB
```

Then make the acquisition decision based on evidence rather than convenience.

**The implementation should begin only after this audit gives us a clean initial corpus and provenance policy.**
