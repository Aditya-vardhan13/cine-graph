export type PinnedEvidence = {
  chunk_id: string;
  film_entity_id: string;
  section_title: string;
  source_url: string;
  source_revision: string | null;
};

export type WriterDecision = {
  id: string;
  created_at: string;
  question: string;
  films: Array<{ entity_id: string; title: string }>;
  decision: string;
  sources: string[];
  version?: 2;
  first_mechanism?: string;
  second_mechanism?: string;
  contrast?: string;
  evidence?: PinnedEvidence[];
};

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
        lines.push(`- ${film?.title || "Film"}, ${item.section_title}: <${item.source_url}> (revision: ${item.source_revision || "unavailable"}; passage: ${item.chunk_id})`);
      }
    } else {
      for (const source of note.sources) lines.push(`- <${source}>`);
    }
  }
  return `${lines.join("\n")}\n`;
}
