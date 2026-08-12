export type Film = {
  id: string;
  title: string;
  release_date: string | null;
  runtime_minutes: number | null;
  genres: string[];
  language_code: string;
};

export type Health = {
  status: string;
  films: number;
  people: number;
  credits: number;
  sources: number;
  latest_ingestion_at: string | null;
  language_editions: Array<{
    code: string;
    display_name: string;
    native_name: string | null;
    script: string;
    enabled: boolean;
    status: string;
  }>;
};

export type FilmDetail = Film & {
  wikidata_id: string | null;
  countries: string[];
  aliases: string[];
  credits: Array<{ person_id: string; name: string; role: string; character_name: string | null }>;
  provenance: Array<{ source_name: string; source_url: string; license: string; field_name: string; source_reference: string }>;
};

export type SimilarFilm = Film & {
  score: number;
  factors: Array<{ label: string; weight: number; contribution: number; evidence: string }>;
};

export type ConnectionSignal = { label: string; weight: number; contribution: number; evidence: string };

export type FilmComparison = {
  first: Film;
  second: Film;
  summary: string;
  signals: ConnectionSignal[];
};

export type Graph = {
  center_id: string;
  nodes: Array<{ id: string; label: string; type: string }>;
  edges: Array<{ source: string; target: string; label: string; evidence: string }>;
  truncated: boolean;
};

const baseUrl = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";

export async function api<T>(path: string, revalidate = 0): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { next: { revalidate } });
  if (!response.ok) throw new Error(`API request failed (${response.status})`);
  return response.json() as Promise<T>;
}

export function year(value: string | null) {
  return value?.slice(0, 4) ?? "—";
}
