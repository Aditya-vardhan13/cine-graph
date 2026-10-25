import Link from "next/link";
import { api, CorpusQuality, Film, year } from "../../lib/api";
import { ResearchCatalogSearch } from "../research-catalog-search";

export const dynamic = "force-dynamic";

export default async function CatalogPage() {
  let quality: CorpusQuality | null = null;
  let films: Film[] = [];
  try { [quality, films] = await Promise.all([api<CorpusQuality>("/corpus/quality", 10), api<Film[]>("/films?limit=8", 10)]); }
  catch { /* Search remains available through the browser API when server rendering cannot reach it. */ }
  return <main className="shell journey-page">
    <section className="page-intro"><p className="eyebrow">Film library</p><h1>Find a film to study.</h1><p>Search the writer collection first. Each film opens a focused source dossier. Structured metadata profiles are available below when you need cast, crew, and provenance.</p></section>
    <ResearchCatalogSearch count={quality?.research.films} />
    <section className="catalog-preview"><div><p className="eyebrow">Structured profiles</p><h2>People, credits, and explicit connections</h2><p>These older metadata records are separate from the narrative writer collection. Verify provenance before using a field.</p></div><div className="catalog-preview-grid">{films.map((film) => <Link key={film.id} href={`/films/${film.id}`}><small>{year(film.release_date)}</small><strong>{film.title}</strong><span>View metadata ↗</span></Link>)}</div></section>
  </main>;
}
