"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Film, FilmComparison, Health, year } from "../lib/api";

type Props = { health: Health | null; initialFilms: Film[]; initialError: string | null };

const metric = (value: number | undefined) => value?.toLocaleString("en-IN") ?? "—";

export function Explorer({ health, initialFilms, initialError }: Props) {
  const [films] = useState(initialFilms);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Film[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [message, setMessage] = useState(initialError);
  const [firstFilm, setFirstFilm] = useState<Film | null>(null);
  const [secondFilm, setSecondFilm] = useState<Film | null>(null);
  const [comparison, setComparison] = useState<FilmComparison | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
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

  const readyToCompare = Boolean(firstFilm && secondFilm && firstFilm.id !== secondFilm.id);
  const remainingSlot = firstFilm ? "second" : "first";

  async function chooseFilm(film: Film) {
    if (!firstFilm) setFirstFilm(film);
    else if (!secondFilm || secondFilm.id !== film.id) setSecondFilm(film);
    setQuery("");
    setSuggestions([]);
    setSearchedQuery("");
    setMessage(null);
  }

  async function compare() {
    if (!readyToCompare || !firstFilm || !secondFilm) return;
    setComparisonLoading(true);
    setMessage(null);
    try {
      const response = await fetch(`${apiUrl}/films/compare?first_id=${firstFilm.id}&second_id=${secondFilm.id}`);
      if (!response.ok) {
        if (response.status === 404 || response.status === 422) {
          throw new Error("stale-api");
        }
        throw new Error("comparison-failed");
      }
      setComparison(await response.json());
    } catch (error) {
      setMessage(error instanceof Error && error.message === "stale-api"
        ? "Connection Lens needs the updated API. Rebuild or restart the FastAPI service, then try again."
        : "The connection analysis could not reach the catalog. Please try again.");
    } finally {
      setComparisonLoading(false);
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
          <h1>What connects<br />these films?</h1>
          <p className="intro">A cinema rabbit hole with receipts. Trace the collaborators, genre DNA and release-era context that actually link two films.</p>
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

      <section className="connection-lens">
        <div className="lens-copy"><p className="eyebrow">Connection lens</p><h2>Put two films on the table.</h2><p>Start with any title. CineGraph shows only the links it can prove from the current catalog.</p></div>
        <div className="lens-workspace">
          <div className="film-slots"><FilmSlot film={firstFilm} label="First film" onClear={() => { setFirstFilm(null); setComparison(null); }} /><span className="versus">×</span><FilmSlot film={secondFilm} label="Second film" onClear={() => { setSecondFilm(null); setComparison(null); }} /></div>
          <div className="live-search"><span className="search-glyph">⌕</span><input autoComplete="off" aria-label={`Search for ${remainingSlot} film`} value={query} onChange={(event) => setQuery(event.target.value)} placeholder={firstFilm ? "Replace or add a second film…" : "Start typing a film title…"} /><span className="search-state">{searching ? "Searching" : "Live"}</span>{(suggestions.length > 0 || searchError || (searchedQuery === query.trim() && query.trim().length >= 2 && !searching)) && <div className="suggestions">{searchError ? <p className="search-feedback error">{searchError}</p> : suggestions.length ? suggestions.map((film) => <button key={film.id} onClick={() => chooseFilm(film)}><span><b>{film.title}</b><small>{year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Metadata only"}</small></span><i>add ↗</i></button>) : <p className="search-feedback">No title matches “{query.trim()}”. Try fewer words.</p>}</div>}</div>
          <button className="compare-button" onClick={compare} disabled={!readyToCompare || comparisonLoading}>{comparisonLoading ? "Tracing connections…" : "Reveal the connection"}</button>
        </div>
      </section>

      {(comparison || message) && <section className="connection-result">{message && <p className="notice">{message}</p>}{comparison && <><div><p className="eyebrow">Connection report</p><h2>{comparison.summary}</h2><p>{comparison.first.title} <i>×</i> {comparison.second.title}</p></div><div className="signal-list">{comparison.signals.length ? comparison.signals.map((signal) => <article key={signal.label}><span>{signal.label}</span><b>{signal.evidence}</b><small>Evidence weight: {Math.round(signal.weight * 100)}%</small></article>) : <article><span>No hidden match</span><b>These films may still be creatively interesting together—but the current metadata cannot prove a direct connection.</b><small>Screenplay and scene-level evidence arrives in a later phase.</small></article>}</div></>}</section>}

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
