import Link from "next/link";
import { notFound } from "next/navigation";
import { api, ApiRequestError, FilmDetail, Graph, ResearchFilm, SimilarFilm, year } from "../../../lib/api";

function sourceHost(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return "Source"; }
}

export default async function FilmPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let film: FilmDetail;
  try {
    film = await api<FilmDetail>(`/films/${id}`);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) notFound();
    throw error;
  }
  const [graphResult, similarResult, researchResult] = await Promise.allSettled([
    api<Graph>(`/films/${id}/graph`), api<SimilarFilm[]>(`/films/${id}/similar`),
    film.research_available && film.entity_id ? api<ResearchFilm>(`/research/films/${film.entity_id}`) : Promise.resolve(null),
  ]);
  const graph = graphResult.status === "fulfilled" ? graphResult.value : null;
  const similar = similarResult.status === "fulfilled" ? similarResult.value : null;
  const research = researchResult.status === "fulfilled" ? researchResult.value : null;
  const displayYear = research?.release_year ?? film.research_release_year ?? year(film.release_date);
  const displayRuntime = research?.runtime_minutes ?? film.runtime_minutes;
  const displayLanguage = research?.language_code ?? film.language_code;
  const displayGenres = research?.genres.length ? research.genres : film.genres;
  const sourcedCredits = film.sourced_credit_groups?.find((group) => group.credits.some((credit) => credit.character_name)) || film.sourced_credit_groups?.[0];
  const releaseSource = research?.metadata_evidence.release_event?.[0]?.source_url || film.research_release_source_url;
  const meaningfulSimilar = similar?.filter((item) => item.factors.some((factor) => factor.label !== "Release era")) || [];
  const hasGraphPeople = Boolean(graph?.nodes.some((node) => node.type === "person"));
  const researchSources = Object.entries(research?.metadata_evidence || {}).flatMap(([field, entries]) =>
    Array.from(new Map(entries.map((entry) => [entry.source_url, entry])).values()).map((entry) => ({ field, ...entry })));
  return <main className="shell detail-shell">
    <Link href="/catalog" className="back">← Back to catalog</Link>
    <section className="film-hero">
      <div className="detail-poster"><span>{displayYear}</span><b>{film.title.slice(0, 1)}</b></div>
      <div><p className="eyebrow">Film profile</p><h1>{film.title}</h1><p className="metadata">{research?.release_date || displayYear} <i>·</i> {displayRuntime ? `${displayRuntime} minutes` : research?.metadata_issues.includes("runtime_requires_version_or_value_resolution") ? "Runtime disputed by sources" : "Runtime unavailable"} <i>·</i> Original language: {displayLanguage.toUpperCase()}</p><div className="pills large">{displayGenres.map((genre) => <span key={genre}>{genre}</span>)}</div><p className="detail-intro">{research ? "Source-linked research metadata is shown where available; older catalog fields fill remaining gaps." : "This profile uses older catalog metadata; check provenance before relying on a field."} {releaseSource && <a href={releaseSource} target="_blank" rel="noopener noreferrer">Inspect release source ↗</a>}</p>{film.release_year_conflict && <p className="release-conflict">The legacy profile records {year(film.release_date)}, but research assertions identify {film.research_release_year} as the earliest recorded release year.</p>}{!film.research_release_year && film.release_date && <p className="release-caveat">Release year shown from the legacy profile; not yet cross-checked in the writer collection.</p>}{film.research_available && film.entity_id ? <Link className="detail-study-link" href={`/research/${film.entity_id}`}>Study this film as a writer ↗</Link> : <p className="detail-research-unavailable">Writer comparison is not yet available for this catalog title.</p>}</div>
    </section>

    <section className="detail-grid">
      <div className="panel credits"><p className="eyebrow">Credits</p><h2>People and characters</h2>{sourcedCredits ? <><p className="detail-intro">Credits as reported by {sourcedCredits.source_name}; source lists may be incomplete. {sourcedCredits.rights_status === "local_noncommercial_only" && "This source is licensed for local non-commercial use only."}</p>{["director", "writer", "cast"].map((role) => { const entries = sourcedCredits.credits.filter((credit) => credit.role === role); return entries.length ? <div className="credit-row" key={role}><span>{role}</span><div>{entries.slice(0, role === "cast" ? 12 : 5).map((credit, index) => <a key={`${credit.name}-${role}-${index}`} href={credit.source_url} target="_blank" rel="noopener noreferrer">{credit.name}{credit.character_name ? ` as ${credit.character_name}` : ""}</a>)}</div></div> : null; })}<small>{sourcedCredits.source_license} · open a name to inspect the source</small></> : film.credits.length ? ["director", "writer", "cast"].map((role) => { const entries = film.credits.filter((credit) => credit.role === role); return entries.length ? <div className="credit-row" key={role}><span>{role}</span><div>{entries.slice(0, role === "cast" ? 8 : 4).map((credit) => <Link key={`${credit.person_id}-${role}`} href={`/people/${credit.person_id}`}>{credit.name}{credit.character_name ? ` as ${credit.character_name}` : ""}</Link>)}</div></div> : null; }) : <p className="muted">No reviewed credits are available for this profile yet.</p>}</div>
      <div className="panel graph"><p className="eyebrow">Relationship graph</p><h2>Direct connections</h2>{graph && hasGraphPeople ? <GraphView graph={graph} /> : <p role="status" className="muted">No reviewed person graph links are available for this profile yet. Source-reported credits above remain attributed to their source.</p>}</div>
    </section>

    <section className="panel similarity"><div><p className="eyebrow">Evidence-backed paths</p><h2>Where to go next</h2><p>Only shared creative people or genres count as a catalog lead here. A matching release year alone is not a meaningful connection.</p></div><div className="similar-list">{meaningfulSimilar.length ? meaningfulSimilar.map((item) => <Link href={`/films/${item.id}`} key={item.id} className="similar"><div><b>{item.title}</b><small>{item.factors.filter((factor) => factor.label !== "Release era").map((factor) => `${factor.label}: ${factor.evidence}`).join(" · ")}</small></div><span>↗</span></Link>) : <p role="status" className="muted">No meaningful catalog connection is available yet. {film.research_available && film.entity_id && <Link href={`/research/${film.entity_id}`}>Explore this film’s source passages instead ↗</Link>}</p>}</div></section>

    <section className="panel provenance"><p className="eyebrow">Evidence</p><h2>Field provenance</h2><div className="source-table">{film.provenance.map((entry, index) => <a key={`${entry.field_name}-${index}`} href={entry.source_reference} target="_blank" rel="noopener noreferrer"><span>{entry.field_name.replaceAll("_", " ")}</span><b>{entry.source_name}</b><small>{entry.license}</small><i>↗</i></a>)}{researchSources.map((entry) => <a key={`${entry.field}-${entry.assertion_id}`} href={entry.source_url} target="_blank" rel="noopener noreferrer"><span>{entry.field.replaceAll("_", " ")}</span><b>{sourceHost(entry.source_url)}</b><small>Revision {entry.source_revision ? `${entry.source_revision.slice(0, 12)}${entry.source_revision.length > 12 ? "…" : ""}` : "not supplied"} · {entry.review_status}</small><i>↗</i></a>)}</div>{!film.provenance.length && !researchSources.length && <p className="muted">No inspectable field source is available for this profile yet.</p>}</section>
  </main>;
}

function GraphView({ graph }: { graph: Graph }) {
  const center = graph.nodes.find((node) => node.type === "film");
  const people = graph.nodes.filter((node) => node.type === "person").slice(0, 10);
  return <div className="graph-view"><div className="graph-center">{center?.label}</div><div className="graph-people">{people.map((person, index) => { const edge = graph.edges.find((item) => item.source === person.id); return <div className="graph-person" key={person.id}><span className={`dot dot-${index % 4}`} /><div><b>{person.label}</b><small>{edge?.label}</small></div></div>; })}</div>{graph.truncated && <p className="muted">Showing the strongest direct connections.</p>}</div>;
}
