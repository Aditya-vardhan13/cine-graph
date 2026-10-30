import assert from "node:assert/strict";
import test from "node:test";
import { selectDraftEvidence } from "../lib/story-brief-evidence.ts";

const pin = (film, chunk) => ({
  film_entity_id: film, chunk_id: chunk, section_title: "Plot",
  source_url: "https://example.org/source", source_revision: "1",
});

test("only the writer's pinned passages for the two chosen films reach synthesis", () => {
  const result = selectDraftEvidence([pin("A", "a1"), pin("other", "x"), pin("B", "b1")], "A", "B");
  assert.deepEqual(result, { ready: true, firstIds: ["a1"], secondIds: ["b1"] });
});

test("drafting fails closed on missing, excessive, or duplicate pins", () => {
  assert.equal(selectDraftEvidence([pin("A", "a1")], "A", "B").ready, false);
  assert.equal(selectDraftEvidence([
    pin("A", "a1"), pin("A", "a2"), pin("A", "a3"), pin("A", "a4"), pin("B", "b1"),
  ], "A", "B").ready, false);
  assert.equal(selectDraftEvidence([pin("A", "shared"), pin("B", "shared")], "A", "B").ready, false);
});
