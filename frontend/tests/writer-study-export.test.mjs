import assert from "node:assert/strict";
import { test } from "node:test";
import { parseWriterDecisionArchive, renderWriterDecisionsMarkdown } from "../lib/writer-study-export.ts";

test("exports writer interpretation with provenance, without claiming film fact", () => {
  const markdown = renderWriterDecisionsMarkdown([{
    id: "note-1", created_at: "2026-09-27T00:00:00.000Z",
    question: "How does the antagonist test the hero's ethics?",
    films: [{ entity_id: "a", title: "First" }, { entity_id: "b", title: "Second" }],
    first_mechanism: "Pressure through a false choice.",
    second_mechanism: "Pressure through a public choice.",
    contrast: "Private versus public stakes.",
    decision: "Make the choice visible to the community.",
    sources: ["https://example.org/first"],
    evidence: [{ chunk_id: "chunk-1", film_entity_id: "a", section_title: "Plot", source_url: "https://example.org/first", source_revision: "123", source_license: "CC BY-SA 4.0", passage_preview: "The choice has a public cost." }],
  }]);

  assert.match(markdown, /writer's interpretations and creative choices, not verified film facts/);
  assert.match(markdown, /First — my reading/);
  assert.match(markdown, /My original move:.*visible to the community/);
  assert.match(markdown, /https:\/\/example\.org\/first/);
  assert.match(markdown, /revision: 123; passage: chunk-1/);
  assert.match(markdown, /licence: CC BY-SA 4\.0/);
  assert.match(markdown, /Passage preview: The choice has a public cost/);
});

test("archive import validates notes before accepting any of them", () => {
  const valid = {
    id: "one", created_at: "2026-09-27T00:00:00.000Z", question: "What changes?",
    films: [{ entity_id: "a", title: "First" }], decision: "Try another turn.",
    sources: ["https://example.org/source"],
  };
  assert.deepEqual(parseWriterDecisionArchive([valid, valid]), [valid]);
  assert.throws(() => parseWriterDecisionArchive([valid, { ...valid, id: "two", sources: [7] }]), /invalid note/);
  assert.throws(() => parseWriterDecisionArchive([{ ...valid, sources: ["javascript:alert(1)"] }]), /invalid note/);
  assert.throws(() => parseWriterDecisionArchive({ notes: [valid] }), /not a supported list/);
});

test("older notes retain source links", () => {
  const markdown = renderWriterDecisionsMarkdown([{
    id: "note-1", created_at: "2026-09-27T00:00:00.000Z",
    question: "What changes?", films: [], decision: "Try another turn.",
    sources: ["https://example.org/source"],
  }]);
  assert.match(markdown, /https:\/\/example\.org\/source/);
});
