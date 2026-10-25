import Link from "next/link";
import { notFound } from "next/navigation";
import { api, ApiRequestError, ResearchFilm } from "../../../lib/api";
import { FilmDossier } from "../../story-comparison";

export default async function ResearchFilmPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let film: ResearchFilm;
  try { film = await api<ResearchFilm>(`/research/films/${encodeURIComponent(id)}`); }
  catch (error) { if (error instanceof ApiRequestError && error.status === 404) notFound(); throw error; }
  return <main className="shell journey-page research-page">
    <div className="route-back"><Link href="/catalog">← Film library</Link><Link href={`/study?study=${film.entity_id}`}>Bring into a comparison ↗</Link></div>
    <FilmDossier film={film} />
  </main>;
}
