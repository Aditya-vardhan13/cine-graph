"use client";

import { useEffect, useState } from "react";
import { Film, FilmLineage, year } from "../lib/api";

export function LineageExplorer({ lineageEntryPoints }: { lineageEntryPoints: Film[] }) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Film[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Film | null>(null);
  const [lineage, setLineage] = useState<FilmLineage | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    const normalized = query.trim();
    setSuggestions([]);
    setSearchedQuery("");
    setSearchError(null);
    if (normalized.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await fetch(`/api/v1/films?q=${encodeURIComponent(normalized)}&limit=7`, { signal: controller.signal });
        if (!response.ok) throw new Error();
        const results: Film[] = await response.json();
        if (!controller.signal.aborted) { setSuggestions(results); setSearchedQuery(normalized); }
      } catch { if (!controller.signal.aborted) setSearchError("Live title search is unavailable. Try again later."); }
      finally { if (!controller.signal.aborted) setSearching(false); }
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  function chooseFilm(film: Film) {
    setSelected(film); setQuery(""); setSuggestions([]); setSearchedQuery(""); setLineage(null); setMessage(null);
  }

  async function traceLineage() {
    if (!selected) return;
    setLoading(true); setMessage(null); setLineage(null);
    try {
      const response = await fetch(`/api/v1/films/${selected.id}/lineage`);
      if (!response.ok) throw new Error();
      setLineage(await response.json());
    } catch { setMessage("The lineage route could not be loaded. Please try again."); }
    finally { setLoading(false); }
  }

  return <>
    <section className="page-intro"><p className="eyebrow">Typed film relationships</p><h1>Follow a proven story route.</h1><p>Look up an installment, adaptation, or source-material relationship. Genre or cast similarity never becomes a lineage claim.</p></section>
    <section className="connection-lens lineage-workbench">
      <div className="lens-copy"><p className="eyebrow">Start with one film</p><h2>What came before it?</h2><p>Choose a title and inspect only the direct links that the catalog can source.</p>{lineageEntryPoints.length > 0 && <div className="lineage-entry-points"><span>Try a proven route</span>{lineageEntryPoints.slice(0, 6).map((film) => <button key={film.id} onClick={() => chooseFilm(film)}>{film.title}</button>)}</div>}</div>
      <div className="lens-workspace">
        <div className="film-slots single"><div className={selected ? "film-slot selected" : "film-slot"}><span>Selected film</span><b>{selected?.title ?? "Waiting for a title"}</b><small>{selected ? `${year(selected.release_date)} · ${selected.genres.slice(0, 2).join(", ")}` : "Use the live search below"}</small>{selected && <button aria-label={`Remove ${selected.title}`} onClick={() => { setSelected(null); setLineage(null); }}>×</button>}</div></div>
        <div className="live-search"><span className="search-glyph">⌕</span><input autoComplete="off" aria-label="Search for a film" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search a film title…" /><span className="search-state">{searching ? "Searching" : "Live"}</span>{(suggestions.length > 0 || searchError || (searchedQuery === query.trim() && query.trim().length >= 2 && !searching)) && <div className="suggestions">{searchError ? <p className="search-feedback error">{searchError}</p> : suggestions.length ? suggestions.map((film) => <button key={film.id} onClick={() => chooseFilm(film)}><span><b>{film.title}</b><small>{year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Metadata only"}</small></span><i>trace ↗</i></button>) : <p className="search-feedback">No title matches “{query.trim()}”. Try fewer words.</p>}</div>}</div>
        <button className="compare-button" onClick={traceLineage} disabled={!selected || loading}>{loading ? "Tracing lineage…" : "Trace story lineage"}</button>
      </div>
    </section>
    {(lineage || message) && <section className="connection-result" aria-live="polite">{message && <p className="notice">{message}</p>}{lineage && <><div><p className="eyebrow">Lineage report</p><h2>{lineage.summary}</h2><p>{lineage.film.title}</p></div><div className="signal-list">{lineage.edges.length ? lineage.edges.map((edge) => <article key={edge.assertion_id}><span>{edge.relation_label} <i>·</i> {edge.direction}</span><b>{edge.target_film?.title ?? edge.target_title}</b><p className="writer-question">{edge.writer_question}</p><small>{edge.target_kind} <i>·</i> {edge.assertion_kind === "source_fact" ? "Source-backed fact" : edge.assertion_kind}</small>{edge.evidence_url && <a href={edge.evidence_url} target="_blank" rel="noopener noreferrer">View evidence ↗</a>}</article>) : <article><span>No typed route for this title</span><b>The catalog has no explicit source relationship for this film yet.</b><small>Try a proven route above. CineGraph will not substitute genre, era, or cast overlap.</small></article>}</div></>}</section>}
  </>;
}
