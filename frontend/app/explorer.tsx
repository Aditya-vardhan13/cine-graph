"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CorpusQuality, Film, FilmLineage, Health, year } from "../lib/api";

type Props = { health: Health | null; corpusQuality: CorpusQuality | null; initialFilms: Film[]; lineageEntryPoints: Film[]; initialError: string | null };

const metric = (value: number | undefined) => value?.toLocaleString("en-IN") ?? "—";

export function Explorer({ health, corpusQuality, initialFilms, lineageEntryPoints, initialError }: Props) {
  const [films] = useState(initialFilms);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Film[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [message, setMessage] = useState(initialError);
  const [firstFilm, setFirstFilm] = useState<Film | null>(null);
  const [lineage, setLineage] = useState<FilmLineage | null>(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const apiUrl = "/api/v1";

  useEffect(() => {
    const normalized = query.trim();
    if (normalized.length < 2) { setSuggestions([]); setSearchError(null); setSearchedQuery(""); return; }
    let active = true;
    const timer = window.setTimeout(async () => {
      setSearching(true);
      setSearchError(null);
      try {
        const response = await fetch(`${apiUrl}/films?q=${encodeURIComponent(normalized)}&limit=7`);
        if (!response.ok) throw new Error();
        const results: Film[] = await response.json();
        if (active) { setSuggestions(results); setSearchedQuery(normalized); }
      } catch {
        if (active) {
          setSuggestions([]);
          setSearchError("Live search is unavailable. Check that the API is running, then try again.");
          setSearchedQuery(normalized);
        }
      }
      finally { if (active) setSearching(false); }
    }, 180);
    return () => { active = false; window.clearTimeout(timer); };
  }, [apiUrl, query]);

  const readyToTrace = Boolean(firstFilm);

  async function chooseFilm(film: Film) {
    setFirstFilm(film);
    setQuery("");
    setSuggestions([]);
    setSearchedQuery("");
    setLineage(null);
    setMessage(null);
  }

  async function traceLineage() {
    if (!firstFilm) return;
    setLineageLoading(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiUrl}/films/${firstFilm.id}/lineage`);
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error("stale-api");
        }
        throw new Error("lineage-failed");
      }
      setLineage(await response.json());
    } catch (error) {
      setMessage(error instanceof Error && error.message === "stale-api"
        ? "Story Lineage needs the updated API. Rebuild or restart the FastAPI service, then try again."
        : "The lineage analysis could not reach the catalog. Please try again.");
    } finally {
      setLineageLoading(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <Link href="/" className="brand"><span>C</span> CineGraph</Link>
        <p>Public-data Cinema Explorer <i>·</i> Phase A</p>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">English-language catalog</p>
          <h1>Trace a story<br />to its roots.</h1>
          <p className="intro">A cinema rabbit hole with receipts. Follow only the direct installment, adaptation and source-material routes the catalog can prove.</p>
        </div>
        <aside className="source-card">
          <span className="signal" />
          <div><strong>Source: Wikidata</strong><small>CC0 structured metadata · provenance retained</small></div>
          <a href="https://www.wikidata.org/" target="_blank">View source ↗</a>
        </aside>
      </section>

      <section className="metrics" aria-label="Catalog health">
        <Metric label="Films" value={metric(health?.films)} />
        <Metric label="People" value={metric(health?.people)} />
        <Metric label="Credits" value={metric(health?.credits)} />
        <Metric label="Active edition" value={health?.language_editions.find((edition) => edition.enabled)?.display_name ?? "—"} />
      </section>

      {corpusQuality && <section className="quality-board">
        <div><p className="eyebrow">Corpus quality board</p><h2>Know what the catalog knows.</h2><p>Facts, relationships and narrative material are counted separately so a connection never looks stronger than its evidence.</p></div>
        <div className="quality-metrics"><Metric label="Release events" value={metric(corpusQuality.release_events)} /><Metric label="Explicit work links" value={metric(corpusQuality.explicit_work_relationships)} /><Metric label="Reference sources" value={metric(corpusQuality.sources.length)} /></div>
        <div className="source-quality-list">{corpusQuality.sources.map((source) => <article key={source.source_name}><div><span>{source.source_name}</span><small>{source.license}</small></div><p>{metric(source.records)} source records <i>·</i> {metric(source.matched)} reconciled <i>·</i> {metric(source.narrative_documents)} narrative documents</p></article>)}</div>
      </section>}

      <section className="connection-lens">
        <div className="lens-copy"><p className="eyebrow">Story lineage</p><h2>Start with one film.</h2><p>Trace its direct installment, adaptation and source-material routes. Similarity never becomes a claim.</p>{lineageEntryPoints.length > 0 && <div className="lineage-entry-points"><span>Try a proven route</span>{lineageEntryPoints.slice(0, 6).map((film) => <button key={film.id} onClick={() => chooseFilm(film)}>{film.title}</button>)}</div>}</div>
        <div className="lens-workspace">
          <div className="film-slots single"><FilmSlot film={firstFilm} label="Selected film" onClear={() => { setFirstFilm(null); setLineage(null); }} /></div>
          <div className="live-search"><span className="search-glyph">⌕</span><input autoComplete="off" aria-label="Search for a film" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={firstFilm ? "Replace this film…" : "Start typing a film title…"} /><span className="search-state">{searching ? "Searching" : "Live"}</span>{(suggestions.length > 0 || searchError || (searchedQuery === query.trim() && query.trim().length >= 2 && !searching)) && <div className="suggestions">{searchError ? <p className="search-feedback error">{searchError}</p> : suggestions.length ? suggestions.map((film) => <button key={film.id} onClick={() => chooseFilm(film)}><span><b>{film.title}</b><small>{year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Metadata only"}</small></span><i>trace ↗</i></button>) : <p className="search-feedback">No title matches “{query.trim()}”. Try fewer words.</p>}</div>}</div>
          <button className="compare-button" onClick={traceLineage} disabled={!readyToTrace || lineageLoading}>{lineageLoading ? "Tracing lineage…" : "Trace story lineage"}</button>
        </div>
      </section>

      {(lineage || message) && <section className="connection-result">{message && <p className="notice">{message}</p>}{lineage && <><div><p className="eyebrow">Lineage report</p><h2>{lineage.summary}</h2><p>{lineage.film.title}</p></div><div className="signal-list">{lineage.edges.length ? lineage.edges.map((edge) => <article key={edge.assertion_id}><span>{edge.relation_label} <i>·</i> {edge.direction}</span><b>{edge.target_film?.title ?? edge.target_title}</b><p className="writer-question">{edge.writer_question}</p><small>{edge.target_kind} <i>·</i> {edge.assertion_kind === "source_fact" ? "Source-backed fact" : edge.assertion_kind}</small>{edge.evidence_url && <a href={edge.evidence_url} target="_blank">View evidence ↗</a>}</article>) : <article><span>No typed route for this title</span><b>The catalog has no explicit source relationship for this film yet.</b><small>Try a proven route above. CineGraph will not substitute genre, era or cast overlap for a relationship.</small></article>}</div></>}</section>}

      <section className="catalog">
        <div className="catalog-heading">
          <div><p className="eyebrow">Curated entry points</p><h2>Start a rabbit hole</h2></div>
          <p className="catalog-note">Open a film to see its people graph and transparent related-film signals.</p>
        </div>
        <div className="film-grid">
          {films.map((film, index) => <FilmCard key={film.id} film={film} index={index} />)}
        </div>
      </section>

      <section className="editions">
        <div><p className="eyebrow">Language editions</p><h2>Built to expand beyond English.</h2><p>Core film, person, credit, alias and provenance records are language-neutral. Telugu, Tamil and Hindi are visibly prepared—not silently mixed into the English dataset.</p></div>
        <div className="edition-list">{health?.language_editions.map((edition) => <div key={edition.code} className={edition.enabled ? "edition live" : "edition"}><span>{edition.native_name ?? edition.display_name}</span><small>{edition.enabled ? "Live" : "Planned"}</small></div>)}</div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="metric"><strong>{value}</strong><span>{label}</span></div>; }

function FilmCard({ film, index }: { film: Film; index: number }) {
  return <Link href={`/films/${film.id}`} className="film-card">
    <div className={`poster poster-${index % 6}`}><span>{year(film.release_date)}</span><b>{film.title.slice(0, 1)}</b></div>
    <div><h3>{film.title}</h3><p>{year(film.release_date)} <i>·</i> {film.runtime_minutes ? `${film.runtime_minutes} min` : "Runtime unavailable"}</p><div className="pills">{film.genres.slice(0, 2).map((genre) => <span key={genre}>{genre}</span>)}</div></div>
  </Link>;
}

function FilmSlot({ film, label, onClear }: { film: Film | null; label: string; onClear: () => void }) {
  return <div className={film ? "film-slot selected" : "film-slot"}>{film ? <><span>{label}</span><b>{film.title}</b><small>{year(film.release_date)} · {film.genres.slice(0, 2).join(", ")}</small><button aria-label={`Remove ${film.title}`} onClick={onClear}>×</button></> : <><span>{label}</span><b>Waiting for a title</b><small>Use the live search below</small></>}</div>;
}
