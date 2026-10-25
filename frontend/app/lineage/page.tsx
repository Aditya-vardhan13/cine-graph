import { api, Film } from "../../lib/api";
import { LineageExplorer } from "../explorer";

export const dynamic = "force-dynamic";

export default async function LineagePage() {
  let entryPoints: Film[] = [];
  try { entryPoints = await api<Film[]>("/lineage/entry-points", 10); }
  catch { /* The title search remains available if entry points cannot be fetched. */ }
  return <main className="shell journey-page"><LineageExplorer lineageEntryPoints={entryPoints} /></main>;
}
