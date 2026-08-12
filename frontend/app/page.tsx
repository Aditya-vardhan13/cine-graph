import { Explorer } from "./explorer";
import { api, CorpusQuality, Film, Health } from "../lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  let health: Health | null = null;
  let corpusQuality: CorpusQuality | null = null;
  let initialFilms: Film[] = [];
  let lineageEntryPoints: Film[] = [];
  let error: string | null = null;
  try {
    [health, initialFilms, lineageEntryPoints] = await Promise.all([
      api<Health>("/health", 10), api<Film[]>("/films?limit=12", 10), api<Film[]>("/lineage/entry-points", 10),
    ]);
    corpusQuality = await api<CorpusQuality>("/corpus/quality", 10);
  } catch {
    error = "The Explorer API is unavailable. Start the FastAPI service, then refresh this page.";
  }
  return <Explorer health={health} corpusQuality={corpusQuality} initialFilms={initialFilms} lineageEntryPoints={lineageEntryPoints} initialError={error} />;
}
