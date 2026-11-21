# Explicit retrieval index activation

Status: implemented, not activated. The 4B experiment has not passed its
selection/generation or held-out quality gate and is not the serving index.

`ACTIVE_RETRIEVAL_INDEX_RUN_ID` accepts an existing `EmbeddingIndexRun` UUID.
It pins the evidence chunk run and its model contract for normal retrieval
callers. A newer completed run does not change this selection. No new database,
activation table, vector copy, or schema migration is needed.

The resolver requires the pinned index and its preprocessing run to be
complete and match the requested collection/language. The model must be an
Ollama contract with 1,024 dimensions and a recorded immutable manifest
SHA-256 revision. Requested/completed chunk counters must agree, be nonzero,
and report no failures. The existing embedding adapter checks that the local
model digest agrees before generating a query vector. Source-rights and film
scope checks remain in the retrieval queries.

Missing, failed, mismatched or malformed pinned runs fail closed. They never
select a different run or lexical corpus. This prevents accidental model/text
mixing; it does not establish that stored vectors are semantically good,
source hashes are current, or counters prove actual vector-row integrity.
Those remain build and acceptance checks before activation.

With the variable unset, legacy latest-complete 0.6B selection is preserved
for rollback compatibility until the replacement passes the agreed gates.
This is not a recommendation to continue optimizing that model.

Offline tools that explicitly request `model_name` do not inherit the serving
pin. They may instead pass `index_run_id` explicitly; if both are provided,
the selected model must match. This allows model comparisons without changing
the live application's selection.

The explicit writer-catalog builder now accepts a recovery profile:

```sh
PYTHONPATH=backend python -m app.services.writer_catalog_index --apply \
  --model qwen3-embedding:4b \
  --model-digest df5bd2e3c74cd8d069d21dc038f1b359fcdc9458fce1c99bd43c9eb1518ff907
```

The command writes chunks and vectors to the configured writer collection;
do not run it until the intended collection and eligible snapshots have been
reviewed. It rejects a different local model digest before chunk creation,
checks the pin during embedding and again before import, and does not set the
serving index. The 8B tag is also selectable with its own exact digest. This
builder's existing chunk configuration is not the full-parent representation
used in the 487-passage diagnostic: a successful build is not evidence that
the diagnostic scores apply to the resulting index. Existing programmatic
callers that omit a profile retain the legacy behavior for compatibility.

## Cutover and rollback

1. Finish source eligibility, representation/model contract checks, real
   question evaluation and latency measurement for the candidate index. The
   offline 487-parent ranking JSON is not a persisted serving index.
2. Verify actual vector-row coverage and source/chunk lineage for that run;
   metadata counters alone are insufficient. Confirm the intended collection
   and approved source scope, and that the API can reach the local model.
3. Set the UUID in the API deployment environment and restart that deployment.
   Record the old/new UUID and exact model digest in the release evidence.
   Check the real API reports the selected run and respects source eligibility.
4. Exercise complete, partial and premise-correction questions through the UI.
   An index activation is not a substitute for question-conditioned selection
   or grounded generation. Do not enable an unverified answer generator.
5. Roll back by restoring the previous verified UUID and restarting. Unsetting
   the variable restores legacy latest-run behavior, not an immutable rollback.

No deployment environment was changed by this implementation. Existing
database, raw source and rollback assets remain untouched.
