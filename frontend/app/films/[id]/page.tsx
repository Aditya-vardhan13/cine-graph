import Link from "next/link";
import { notFound } from "next/navigation";
import { api, ApiRequestError, FilmDetail, Graph, SimilarFilm, year } from "../../../lib/api";

export default async function FilmPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let film: FilmDetail;
  try {
    film = await api<FilmDetail>(`/films/${id}`);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) notFound();
    throw error;
  }
  const [graphResult, similarResult] = await Promise.allSettled([
    api<Graph>(`/films/${id}/graph`), api<SimilarFilm[]>(`/films/${id}/similar`),
  ]);
  const graph = graphResult.status === "fulfilled" ? graphResult.value : null;
  const similar = similarResult.status === "fulfilled" ? similarResult.value : null;
  const displayYear = film.research_release_year ?? year(film.release_date);
  return <main className="shell detail-shell">
    <header className="topbar"><Link href="/" className="brand"><span>C</span> CineGraph</Link><p>Film intelligence <i>·</i> public metadata</p></header>
    <Link href="/" className="back">← Back to catalog</Link>
    <section className="film-hero">
      <div className="detail-poster"><span>{displayYear}</span><b>{film.title.slice(0, 1)}</b></div>
      <div><p className="eyebrow">Film profile</p><h1>{film.title}</h1><p className="metadata">{displayYear} <i>·</i> {film.runtime_minutes ? `${film.runtime_minutes} minutes` : "Runtime unavailable"} <i>·</i> Original language: {film.language_code.toUpperCase()}</p><div className="pills large">{film.genres.map((genre) => <span key={genre}>{genre}</span>)}</div><p className="detail-intro">This profile combines older catalog metadata with source-linked research where available. Check the provenance before relying on a field.</p>{film.release_year_conflict && <p className="release-conflict">The legacy profile records {year(film.release_date)}, but the research assertions identify {film.research_release_year} as the earliest recorded release year. {film.research_release_source_url && <a href={film.research_release_source_url} target="_blank" rel="noopener noreferrer">Inspect release source ↗</a>}</p>}{!film.research_release_year && film.release_date && <p className="release-caveat">Release year shown from the legacy profile; not yet cross-checked in the writer collection.</p>}{film.research_available && film.entity_id ? <Link className="detail-study-link" href={`/?study=${film.entity_id}#compare`}>Study this film as a writer ↗</Link> : <p className="detail-research-unavailable">Writer comparison is not yet available for this catalog title.</p>}</div>
    </section>

    <section className="detail-grid">
      <div className="panel credits"><p className="eyebrow">Credits</p><h2>People around this film</h2>{["director", "writer", "cast"].map((role) => { const entries = film.credits.filter((credit) => credit.role === role); return entries.length ? <div className="credit-row" key={role}><span>{role}</span><div>{entries.slice(0, role === "cast" ? 8 : 4).map((credit) => <Link key={`${credit.person_id}-${role}`} href={`/people/${credit.person_id}`}>{credit.name}</Link>)}</div></div> : null; })}</div>
      <div className="panel graph"><p className="eyebrow">Relationship graph</p><h2>Direct connections</h2>{graph ? <GraphView graph={graph} /> : <p role="status" className="muted">Connections are temporarily unavailable. The film profile is still available.</p>}</div>
    </section>

    <section className="panel similarity"><div><p className="eyebrow">Evidence-backed paths</p><h2>Where to go next</h2><p>Each suggestion names the metadata context it shares with this film. Inspect the linked profiles before relying on a connection.</p></div><div className="similar-list">{similar ? similar.map((item) => <Link href={`/films/${item.id}`} key={item.id} className="similar"><div><b>{item.title}</b><small>{item.factors.map((factor) => `${factor.label}: ${factor.evidence}`).join(" · ")}</small></div><span>↗</span></Link>) : <p role="status" className="muted">Related-film suggestions are temporarily unavailable.</p>}</div></section>

    <section className="panel provenance"><p className="eyebrow">Evidence</p><h2>Field provenance</h2><div className="source-table">{film.provenance.map((entry, index) => <a key={`${entry.field_name}-${index}`} href={entry.source_reference} target="_blank"><span>{entry.field_name.replaceAll("_", " ")}</span><b>{entry.source_name}</b><small>{entry.license}</small><i>↗</i></a>)}</div></section>
  </main>;
}

function GraphView({ graph }: { graph: Graph }) {
  const center = graph.nodes.find((node) => node.type === "film");
  const people = graph.nodes.filter((node) => node.type === "person").slice(0, 10);
  return <div className="graph-view"><div className="graph-center">{center?.label}</div><div className="graph-people">{people.map((person, index) => { const edge = graph.edges.find((item) => item.source === person.id); return <div className="graph-person" key={person.id}><span className={`dot dot-${index % 4}`} /><div><b>{person.label}</b><small>{edge?.label}</small></div></div>; })}</div>{graph.truncated && <p className="muted">Showing the strongest direct connections.</p>}</div>;
}
