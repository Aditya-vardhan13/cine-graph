# Retrieval strategy audit: fix the pipeline before changing model size

## Decision

The high-level direction remains sound: retained, attributable film sources,
PostgreSQL/pgvector, lexical + dense retrieval, reranking, and separately labeled
cited synthesis. The current execution and evaluation are not good enough to
conclude that open models are inadequate, or that an 8B download is the fix.

Keep the existing models during the next controlled experiment. Do not add a
new database, scrape another bulk corpus, or tune repeatedly against the same
50 labels to manufacture an 80% result. Improve representation and measurement
first. No working corpus or immutable source snapshot was modified in this audit.

## What was verified

### 1. The 4B reranker is already quantized and its basic inference works

The local Qwen3 reranker config declares 4-bit affine quantization, group size
64. Its prompt and final-token yes/no logit-difference protocol match the
[official model implementation](https://huggingface.co/Qwen/Qwen3-Reranker-4B).
The query embedding adapter also uses the documented instruction/query shape;
indexed documents already include film and section context. There is no evidence
from this inspection of a reversed score or universally broken prompt format.

Four short local controls were run with the existing quantized model:

| Control | Relevant passage logit difference | Irrelevant passage logit difference |
| --- | ---: | ---: |
| Official capital-of-China reference | 5.5 | -14.5 |
| Batman's final choice about Dent's reputation | 3.5625 | -3.5 |

Both orderings were correct. On the short reference, optimized final-token
projection and the ordinary full output differed by 0.0. Peak MLX allocation
was 2,755,493,128 bytes (2.57 GiB); this is allocator memory, not process RSS or
a guarantee that the whole application fits that budget. Individual controls
took 0.56–2.11 seconds after loading, on 85–361 input tokens. This is a smoke
test, not a benchmark score or a product latency SLO.

The offline MLX CLI previously failed to apply the memory/cache settings
described in its report. It now sets a 4 GiB allocation guideline, a 128 MiB
cache limit, clears unused cache between documents, checks disk headroom before
each document, and records peak allocator usage. MLX's limit is a guideline,
not a hard OS/swap cap. No macOS settings were changed.

### 2. The active text is not adequately cleaned

Read-only inspection of the isolated evaluation database found 24,194 eligible
chunks for 1,000 films in chunk run `0892ebfc-8b33-4051-95da-4a239b288e40`
(`spacy-sentencizer-evidence-v3`). Of these, 1,883 (7.8%) matched obvious
Wikipedia presentation markers such as `thumb|`, `alt=`, or unprocessed link/
template delimiters. This is a marker-based audit, not a complete corruption
count. The frozen hybrid/lexical benchmark pool contained 40 such chunks among
408 unique chunks (9.8%).

The working corpus's index metadata points to the same chunk run and 24,194
vectors, using `qwen3-embedding:0.6b`, 1,024 dimensions, and
`film-section-evidence-v1`. This was metadata inspection only, not a test or
write against the working database.

The parser uses regexes for nested wikitext. Image captions containing nested
links are visibly leaking into prose. Paragraph grouping also happens before
sentence chunking, so the downstream retrieval unit does not reliably preserve
the surrounding section's causal or referential context.

### 3. Useful retained evidence is excluded before embeddings can help

`story.*` questions are hard-filtered to Plot; `craft.*` to Production; reception
to a small section-name list. These are SQL exclusions, not soft ranking priors.
The active Dark Knight corpus has four Plot chunks plus nine eligible chunks
under Themes and analysis (five morality/ethics, four terrorism/escalation).
An ordinary story query cannot retrieve those nine analysis chunks. The text
exists; neither a bigger embedding model nor a reranker can recover it after
the candidate filter removes it. Interpretations still require attribution;
opening the candidate pool must not promote them to plot facts.

### 4. Synthesis discards selected evidence

`story_synthesis._prompt` and its cited-source DTO slice each chunk at 1,000
characters. In this active run, 12,813 eligible chunks (53.0%) exceed that
length. If selected, their tails are omitted regardless of where the supporting
event or explanation occurs. The model is then asked to answer from the shortened
text. This is separate from reranker accuracy, but directly affects end-to-end
usefulness. The generation request also hardcodes a 4,096-token context.

Reference-ID validation prevents invented or wrong-film IDs; it does not prove
that generated statements are entailed by those references. That remains an
answer-quality evaluation requirement.

### 5. Offline trials are not the live product

The live comparison use case calls lexical/dense fusion and returns three
source alternatives per film. It does not call the experimental Qwen reranker.
Synthesis is a separate optional request using selected chunk IDs. Promoting
an unverified reranker would have been wrong, but this separation must be clear:
offline improvements are not automatically visible in the website.

### 6. The evaluation needs repair before interpreting percentages

The 50 questions are repeatedly inspected development data, not held-out tests.
One BGE review label explicitly described the Dark Knight opening chunk as the
full plot/ending; the retained text contains neither Dent's final fate nor
Batman's final choice. That label is incorrect. Other comparisons collapse
partial coverage of multi-part questions into one binary value. The Jurassic
Park effects example illustrates this: practical suspense and creature-effect
limitations are different requested facets, supported by different passages.

Preserve the existing scores as experiment history, but do not cite 76%, 52%,
or the candidate-pool oracle as validated model capability/coverage. No corrected
aggregate is asserted here; labels must be re-audited first, without selecting
only changes that raise the score. The 4B embedding trial over 96 already-reviewed
candidates was not a full-corpus 4B retrieval trial either.

The capture tool also retrieves a fresh top-ten pool after calling the live
comparison and scores that pool, rather than faithfully storing only the live
response. All fifty inspected captures did return candidate evidence, so no
abstention skew was observed in this set, but future evaluation must distinguish
UI-path outcomes, candidate recall, and offline reranking. Capture wall time
includes repeated query embedding/retrieval and is not endpoint latency.

## Corrective sequence

1. **Freeze a trustworthy small evaluation.** Retain the current fifty as
   development data. Audit full passages and label exact supporting spans,
   question facets, partial/full support, contradiction, and insufficient
   evidence. Bind reviews to passage content and question hashes, not just IDs.
   Build a fresh film-pair holdout before any release-quality claim. Label
   reviewers and model-assisted judgments honestly; they are not independent
   simply because ranking scores were hidden.
2. **Repair extraction on a ten-film canary.** Use a maintained wikitext parser
   or retained rendered HTML, with fixtures for nested links, images, references,
   templates and quotations. Keep raw revisions immutable. Create versioned new
   derivatives, preserve paragraph/section order, and retain removed citation/
   presentation material separately. Do not rebuild all vectors until this
   canary passes text-quality and evidence-retention checks.
3. **Retrieve smaller evidence, supply adequate context.** Compare paragraph or
   short sentence-window retrieval with its surrounding parent context from the
   same source revision. Use source-backed identity/section metadata, not invented
   thematic descriptions. Replace hard section exclusion with evaluated soft
   priors and an unfiltered film-scoped candidate branch. A comparison may need
   several facets and 2–4 passages per film, not one paragraph to answer everything.
4. **Use the existing models in a controlled ablation.** Compare original vs
   cleaned representation, hard vs soft section selection, and isolated chunks
   vs parent-context evidence while holding the model fixed. Then compare 0.6B
   and quantized 4B on identical pools. Inspect candidate recall before top-rank
   relevance. Do not make 8B or a new vector database a prerequisite.
5. **Make synthesis consume the actual evidence pack.** Pack complete supported
   spans under a tokenizer-aware model budget with reserved output capacity.
   Remove arbitrary character slicing; explicitly report omitted evidence or
   reject an over-budget pack. Preserve source/version/attribution and distinguish
   plot, attributed criticism and generated interpretation. Ask for a contrast
   only where the evidence supports it; otherwise name the gap.
6. **Measure quality and cost separately.** Keep the requested pair-success@1
   diagnostic and its original threshold; add span recall@k, facet coverage of
   the evidence pack, unsupported-claim/citation checks, abstention correctness,
   and answer usefulness. Report cold/warm stage-level p50/p95, peak memory and
   disk headroom. A single top-passage metric is not a paid-product acceptance
   test. Change one variable at a time; no bulk indexing/model sweep until a
   canary demonstrates a gain.

## First ten-film extraction canary and first twenty question review

The initial corrective experiment is now isolated in `cinegraph_eval`. A
versioned `mwparserfromhell` extractor derived new passages from the same ten
retained Wikipedia revisions without rewriting v1 passages or source snapshots.
It preserves image captions under separate source locators. Across 210 article
sections, the read-only comparison found 50 comparable v1 passage units with
obvious markup markers versus zero v2 units, while 4,677 characters of image
captions were retained separately. This marker test does not establish that all
source meaning or citation context survived extraction.

The ten-film v2 canary has 596 derived passages, 580 eligible chunks and 580
locally indexed 0.6B vectors in a separate collection. The unchanged hybrid
retrieval method was then compared on the first 20 frozen questions under
hard-section and whole-film search. A single agent reviewed the 73 distinct
top-ranked passages *without seeing which variant returned them*, marking
direct, partial or irrelevant support. The full question and source passage
content are fingerprint-bound in local ignored review artifacts. This is a
development diagnostic, not an independent gold set or a held-out result.

| Extraction / section policy | Directly supported film sides | Questions with both sides directly supported |
| --- | ---: | ---: |
| v1 / hard section | 26/40 | 9/20 |
| v1 / whole film | 21/40 | 6/20 |
| v2 / hard section | 26/40 | 9/20 |
| v2 / whole film | 20/40 | 5/20 |

Opening every section exposes more candidates but promotes irrelevant cast,
production, reception or legacy text for some plot questions. Parser cleanup
also does not, by itself, improve top-one relevance. Neither change is being
promoted to the live route. Next compare a soft section prior and passage
context within the same frozen candidate pool; retain the hard route as the
control, and audit answer-bearing spans rather than treating visibility as
quality. Some v2 prose still carries bare citation bibliography fragments;
that retention problem also needs a targeted fixture and fix before a wider
rebuild.
Even an oracle allowed to choose independently among these four displayed
heads could directly support both films for only 12/20 questions. That is a
ceiling for *this small head set*, not for the underlying corpus. A selector
over the same four heads cannot meet the requested 16/20 first-stage target;
the next test must inspect deeper candidates and missing source coverage.

The local synthesis prompt no longer slices selected chunks at 1,000
characters. It sends each pinned passage in full when a conservative UTF-8
byte upper bound fits the configured 8,192-token context; otherwise it rejects
the pack and asks for fewer pins before any model request. This protects the
evidence chain, but the prompt's output still requires answer-quality review:
valid reference IDs alone are not entailment proof.
The writer desk now supplies only the passages the writer actually pinned
(one to three per film) to the optional model draft. Changing a pin invalidates
the prior draft instead of leaving a stale interpretation on screen.

## Research grounding and limits

The [Qwen3 Embedding paper](https://arxiv.org/abs/2506.05176) supports considering
open embedding/reranking models at these sizes, not guaranteeing film-domain
accuracy. [Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval)
and [Late Chunking](https://arxiv.org/abs/2409.04701) motivate retaining document
context rather than encoding isolated fragments. Their published gains are not
our gains. In particular, late chunking's token-level pooling cannot simply be
bolted onto Ollama's final-vector API; parent-context retrieval is the simpler
first experiment here. Generated contextual summaries, if tried later, must be
versioned derivatives and never substituted for source text or asserted facts.

No new model download, database replacement, or schema rewrite is justified by
this audit. The next milestone is a measured, reproducible ten-film canary—not
another headline percentage from the already-inspected questions.
