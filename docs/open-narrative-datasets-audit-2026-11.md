# Open narrative data audit — 3 November 2026

## Scope and decision

Search window: **3 May–3 November 2026**. Distinguish first release from
conference publication and recent revisions. Older resources below are explicitly
marked; a recent crawl date is not a publication date. This is a targeted search,
not an exhaustive systematic review.

Start with **SemEval narrative similarity** and **MF² text-only evidence** in an
isolated local evaluation area. Do not merge benchmark questions, answers, false
claims or annotations into the product's corpus or use test data for tuning.
No model runs or product/database changes are part of this acquisition.

## Recent papers and what is actually accessible

| Resource | Date evidence | Useful data / role | Access and licence finding | Decision |
| --- | --- | --- | --- | --- |
| [SemEval-2026 Task 4](https://aclanthology.org/2026.semeval-1.429/), [official data](https://github.com/narrative-similarity-task/narrative-similarity-dataset) | July 2026 proceedings; preprint April 2026; pinned repository commit February 2026 | Human-annotated story triples, theme/action/outcome dimensions and Wikidata references. External narrative-similarity evaluation. | Public JSONL; Wikipedia summaries CC BY-SA 4.0; README describes labels as dual CC-SA 4.0 / CC0. Preserve the exact notice and canary. | Acquired locally; evaluation only. |
| [MF²: How Well Do Vision-Language Models Understand Movies?](https://arxiv.org/abs/2506.06275), [official repository](https://github.com/deep-spin/MF2-bench-how-well-vlms-understand-movies) | First June 2025; revised **19 October 2026**, EMNLP 2026 | 868 manually authored fact/fib pairs over 53 films, category/granularity labels, SRT transcripts and synopses. Attribution, temporal, causal and emotional understanding. | README states CC BY 4.0. Paper describes open-licensed older movies; subtitle provenance is separate from the movie licence. No video downloaded. | Acquire text-only evaluation release; per-asset rights still need review before product reuse. |
| [Do Large Language Models Always Tell The Same Stories?](https://arxiv.org/abs/2606.17350), [repository](https://github.com/thennal10/narrative-similarity) | June 2026; September revision | Narrative-diversity evaluation, human/model comparisons. | Paper explicitly withholds raw Reddit stories/prompts and provides IDs instead; annotations CC BY-SA 4.0. Public repo is not an unrestricted full-text corpus. | Research methods/annotations candidate; not automatic corpus expansion. |
| [SagaQA](https://arxiv.org/abs/2606.03301) | **2 June 2026** | Cross-episode, multi-hop TV narrative questions; generated then filtered annotations. | Paper's linked `https://github.com/galannp/sagaqa` returned 404 during this audit. Paper licence is not proof of dataset access/licence. | Not acquired; do not count as available. |
| [How Technological Innovation Restructures Cultural Space](https://zenodo.org/records/23087224) | **1 October 2026**, v1 | 7,868 U.S. films, production variables, tropes, reviews and rewritten plots. | Compilation CC BY-NC 4.0 with additional non-commercial academic/reproduction terms and upstream restrictions. Includes copyrighted reviews and synthetic summaries. | Do not product-ingest. Metadata/research reference only; 1.7 GB download unnecessary. |

The SemEval paper reports multiple annotations and agreement-based judgments.
Its task compares stories, **not** query-conditioned passage retrieval or useful
writing advice. Its scores cannot substitute for our question/evidence tests.

The MF² paper finds synopsis-only information weaker than subtitles for its
claim-verification task. This does not contradict summaries being useful for
SemEval-style story similarity: the tasks require different granularity.

## Older resources worth retaining, not pretending are new

| Resource | Actual contribution | Access / disposition |
| --- | --- | --- |
| [MovieSum, ACL 2024](https://huggingface.co/datasets/rohitsaxena/MovieSum/raw/main/README.md) | 2,200 screenplay-summary pairs with IMDb IDs; XML scene, character, dialogue and direction structure; 1,800/200/200 splits. | Public release, **CC BY-NC 4.0**. Local non-commercial research candidate, not a cleared product source. Not downloaded this milestone. |
| [NarrativeQA, 2018](https://github.com/google-deepmind/narrativeqa) | Story-level QA, summaries and document links; useful independent single-story comprehension control. | Repo metadata states Apache 2.0; Wikipedia summary and linked full-story rights must be treated separately. Do not execute its full-story downloader indiscriminately. Not acquired. |
| [TRIPOD, 2019](https://github.com/ppapalampidi/TRIPOD) | 99 films with synopsis turning-point annotations and scene-segmented scripts. | Public repo; no explicit reuse licence established in this audit. Research-reference candidate, not approved product ingestion. |
| [STAGE, January 2026](https://arxiv.org/html/2601.08510v1) | 150 films, narrative graphs/events/QA/role-playing; useful schema inspiration. | Appendix B.2 explicitly says raw scripts are **not redistributed**, derived release is non-commercial research, and users obtain originals separately. No working release download was verified. Not acquired. |

Correction to the previous discussion: STAGE is a useful research description,
**not a verified downloadable collection of 150 raw scripts**. Likewise, lack of
full scripts does not by itself explain every current failure. Summaries can
support substantial narrative comparisons; sufficiency is question-specific.

## Local acquisition and reproducibility

Manual command (requires network; never run from ordinary tests):

```sh
conda activate cine-graph
python scripts/acquire_narrative_benchmarks.py --download
```

Pinned release roots under ignored `data/evaluation/external/`:

- `narrative-similarity/ef7375dd08172c804ffa6706aa94d003e59f5015/`
- `mf2/e00ff56479c88fcc9947d4975c8deba93e42e922/`

The command permits only README and approved text-data paths, caps each release
at 25 MB, downloads sequentially with at least one second between requests, and
checks every byte count and Git blob SHA-1 against the pinned tree. The final
local manifest records source URLs, SHA-256, revision and robots status. Existing
files are verified rather than overwritten. HTTP 403/429 stops acquisition;
there is no block bypass or automatic retry loop. Raw download-host robots.txt
returned 404 at acquisition; other errors fail closed. No third-party code runs.

Retain original README licence notices. Dataset release hashes prove capture
integrity, **not** annotation correctness or complete upstream rights clearance.
All raw text and labels stay local; Git contains only this report, acquisition
code and pure policy tests.

### Observed acquisition and structural audit

Both downloads completed. No movie videos, model weights, website crawling or
linked-source scraping was necessary.

- SemEval: **10 files, 6,085,516 bytes**. Track A has 200 development triples,
  39 sample triples and 400 test triples. Track B has 479 development stories,
  108 sample stories and 849 test stories; its test labels contain 400 triples.
  These are alternative task views, not additive independent training examples.
- MF²: **108 files, 4,744,936 bytes**: README, 868-row claims CSV, 53 transcripts
  and 53 synopses. Every referenced film has both text files. All film/claim IDs
  are nonempty and unique; no exact duplicate CSV rows or empty claim strings.
- **Three MF² rows have byte-identical true/false claim strings.** Preserve the
  original capture, flag these as invalid contrastive pairs pending author/source
  review, and exclude them from any paired-accuracy denominator with explicit
  accounting. This is not a licence to silently rewrite their labels.
- SemEval exact story-text overlap: dev/sample **26**, dev/test **164**,
  sample/test **48**. Development has 479 distinct story strings; Track A test
  has 848. These comparisons used hashes without printing test text or answers.
  Official test performance would not establish story-disjoint generalization.
- MF² category fields contain order/spacing differences and trailing commas.
  A versioned adapter should trim/split to sets while preserving raw values.

This audit establishes capture and basic structural issues, **not** independent
validation of every annotation. Film-ID overlap, visual-only support, detailed
licence lineage and source/answer entailment remain to be reviewed before use.

## What happens after acquisition, not yet executed

1. Audit counts, IDs, nonempty inputs, annotation/schema integrity, duplicate
   text and split overlap. SemEval's tracks reuse some data: never add their
   counts as though all are independent examples. Preserve ambiguous labels.
2. Separate evaluation records from model inputs. MF² false claims are test
   queries, never factual evidence. Some claims need video: flag these rather
   than declaring text-only failure to be a model defect.
3. Check film/story overlap with our existing development and holdout sets.
   Official split names alone do not guarantee film-disjointness or absence of
   pretrained-model exposure. Test labels remain out of development prompts.
4. Use SemEval development data for narrative-embedding controls and MF² for
   evidence/claim diagnostics. Neither replaces pairwise, user-question-led
   comparisons or writer judgments of usefulness.
5. Freeze the generation comparison protocol before Qwen 3 4B versus 8B:
   identical source evidence, prompt, context/output budgets and scoring rubric;
   record quantization, sampling, latency and attribution errors. Do not claim
   that dataset acquisition has improved model quality before measuring it.

No fine-tuning, synthetic-data generation, additional graph database, new live
fact source or deployment work is required to establish these baselines.
