export type PinnedEvidence = {
  chunk_id: string;
  film_entity_id: string;
  section_title: string;
  section_locator?: string;
  passage_preview?: string;
  source_url: string;
  source_revision: string | null;
  source_license?: string;
};

export type WriterDecision = {
  id: string;
  created_at: string;
  question: string;
  films: Array<{ entity_id: string; title: string }>;
  decision: string;
  sources: string[];
  version?: 2 | 3;
  first_mechanism?: string;
  second_mechanism?: string;
  contrast?: string;
  evidence?: PinnedEvidence[];
  preprocessing_run_id?: string;
  index_run_id?: string | null;
};

function isSafeSourceUrl(value: unknown): value is string {
  if (typeof value !== "string" || /[<>\s]/.test(value)) return false;
  try { return ["https:", "http:"].includes(new URL(value).protocol); }
  catch { return false; }
}

export function parseWriterDecisionArchive(value: unknown): WriterDecision[] {
  if (!Array.isArray(value) || value.length > 1000) throw new Error("The study archive is not a supported list of notes.");
  const notes: WriterDecision[] = [];
  const seen = new Set<string>();
  for (const item of value) {
    if (!item || typeof item !== "object" ||
      typeof item.id !== "string" || typeof item.created_at !== "string" ||
      typeof item.question !== "string" || typeof item.decision !== "string" ||
      !Array.isArray(item.films) || !item.films.every((film: unknown) =>
        !!film && typeof film === "object" && "entity_id" in film && typeof film.entity_id === "string" &&
        "title" in film && typeof film.title === "string") ||
      !Array.isArray(item.sources) || !item.sources.every(isSafeSourceUrl) ||
      (item.evidence !== undefined && (!Array.isArray(item.evidence) || !item.evidence.every((source: unknown) =>
        !!source && typeof source === "object" && "chunk_id" in source && typeof source.chunk_id === "string" &&
        "film_entity_id" in source && typeof source.film_entity_id === "string" &&
        "source_url" in source && isSafeSourceUrl(source.source_url))))) {
      throw new Error("The study archive contains an invalid note. No notes were imported.");
    }
    if (!seen.has(item.id)) { notes.push(item as WriterDecision); seen.add(item.id); }
  }
  return notes;
}

export function renderWriterDecisionsMarkdown(notes: WriterDecision[]): string {
  const lines = [
    "# CineGraph writer studies",
    "",
    "These are the writer's interpretations and creative choices, not verified film facts. Follow each source link to inspect its context.",
  ];
  for (const note of notes) {
    lines.push(
      "",
      `## ${note.films.map((film) => film.title).join(" × ")}`,
      "",
      `Saved: ${note.created_at}`,
      "",
      `**Writing question:** ${note.question}`,
      "",
    );
    if (note.first_mechanism) lines.push(`**${note.films[0]?.title || "First film"} — my reading:** ${note.first_mechanism}`, "");
    if (note.second_mechanism) lines.push(`**${note.films[1]?.title || "Second film"} — my reading:** ${note.second_mechanism}`, "");
    if (note.contrast) lines.push(`**The difference I see:** ${note.contrast}`, "");
    lines.push(`**My original move:** ${note.decision}`, "", "### Sources to revisit", "");
    if (note.evidence?.length) {
      for (const item of note.evidence) {
        const film = note.films.find((candidate) => candidate.entity_id === item.film_entity_id);
        lines.push(`- ${film?.title || "Film"}, ${item.section_title}: <${item.source_url}> (revision: ${item.source_revision || "unavailable"}; passage: ${item.chunk_id}; licence: ${item.source_license || "unavailable"})`);
        if (item.passage_preview) lines.push(`  - Passage preview: ${item.passage_preview.replace(/\s+/g, " ").slice(0, 240)}`);
      }
    } else {
      for (const source of note.sources) lines.push(`- <${source}>`);
    }
  }
  return `${lines.join("\n")}\n`;
}
