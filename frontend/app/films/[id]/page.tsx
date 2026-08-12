import Link from "next/link";
import { notFound } from "next/navigation";
import { api, FilmDetail, Graph, SimilarFilm, year } from "../../../lib/api";

export default async function FilmPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let film: FilmDetail;
  let graph: Graph;
  let similar: SimilarFilm[];
  try {
    [film, graph, similar] = await Promise.all([api<FilmDetail>(`/films/${id}`), api<Graph>(`/films/${id}/graph`), api<SimilarFilm[]>(`/films/${id}/similar`)]);
  } catch {
    notFound();
  }
  return <main className="shell detail-shell">
    <header className="topbar"><Link href="/" className="brand"><span>C</span> CineGraph</Link><p>Film intelligence <i>·</i> public metadata</p></header>
    <Link href="/" className="back">← Back to catalog</Link>
    <section className="film-hero">
      <div className="detail-poster"><span>{year(film.release_date)}</span><b>{film.title.slice(0, 1)}</b></div>
      <div><p className="eyebrow">Film profile</p><h1>{film.title}</h1><p className="metadata">{year(film.release_date)} <i>·</i> {film.runtime_minutes ? `${film.runtime_minutes} minutes` : "Runtime unavailable"} <i>·</i> Original language: {film.language_code.toUpperCase()}</p><div className="pills large">{film.genres.map((genre) => <span key={genre}>{genre}</span>)}</div><p className="detail-intro">This profile is derived from structured public metadata. Every displayed field links back to its source evidence.</p></div>
    </section>

    <section className="detail-grid">
      <div className="panel credits"><p className="eyebrow">Credits</p><h2>People around this film</h2>{["director", "writer", "cast"].map((role) => { const entries = film.credits.filter((credit) => credit.role === role); return entries.length ? <div className="credit-row" key={role}><span>{role}</span><div>{entries.slice(0, role === "cast" ? 8 : 4).map((credit) => <Link key={`${credit.person_id}-${role}`} href={`/people/${credit.person_id}`}>{credit.name}</Link>)}</div></div> : null; })}</div>
      <div className="panel graph"><p className="eyebrow">Relationship graph</p><h2>Direct connections</h2><GraphView graph={graph} /></div>
    </section>

    <section className="panel similarity"><div><p className="eyebrow">Explainable similarity</p><h2>Related films</h2><p>Scores use shared genres, credited people and release-era proximity. No opaque “vibe” score.</p></div><div className="similar-list">{similar.map((item) => <Link href={`/films/${item.id}`} key={item.id} className="similar"><strong>{item.score}%</strong><div><b>{item.title}</b><small>{item.factors.map((factor) => factor.evidence).join(" · ")}</small></div><span>↗</span></Link>)}</div></section>

    <section className="panel provenance"><p className="eyebrow">Evidence</p><h2>Field provenance</h2><div className="source-table">{film.provenance.map((entry, index) => <a key={`${entry.field_name}-${index}`} href={entry.source_reference} target="_blank"><span>{entry.field_name.replaceAll("_", " ")}</span><b>{entry.source_name}</b><small>{entry.license}</small><i>↗</i></a>)}</div></section>
  </main>;
}

function GraphView({ graph }: { graph: Graph }) {
  const center = graph.nodes.find((node) => node.type === "film");
  const people = graph.nodes.filter((node) => node.type === "person").slice(0, 10);
  return <div className="graph-view"><div className="graph-center">{center?.label}</div><div className="graph-people">{people.map((person, index) => { const edge = graph.edges.find((item) => item.source === person.id); return <div className="graph-person" key={person.id}><span className={`dot dot-${index % 4}`} /><div><b>{person.label}</b><small>{edge?.label}</small></div></div>; })}</div>{graph.truncated && <p className="muted">Showing the strongest direct connections.</p>}</div>;
}
