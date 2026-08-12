import { Explorer } from "./explorer";
import { api, Film, Health } from "../lib/api";

export default async function Home() {
  let health: Health | null = null;
  let initialFilms: Film[] = [];
  let error: string | null = null;
  try {
    [health, initialFilms] = await Promise.all([api<Health>("/health", 10), api<Film[]>("/films?limit=12", 10)]);
  } catch {
    error = "The Explorer API is unavailable. Start the FastAPI service, then refresh this page.";
  }
  return <Explorer health={health} initialFilms={initialFilms} initialError={error} />;
}
