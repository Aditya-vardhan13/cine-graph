"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Film, Health, year } from "../lib/api";

type Props = { health: Health | null; initialFilms: Film[]; initialError: string | null };

const metric = (value: number | undefined) => value?.toLocaleString("en-IN") ?? "—";

export function Explorer({ health, initialFilms, initialError }: Props) {
  const [films, setFilms] = useState(initialFilms);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [message, setMessage] = useState(initialError);

  async function search(event: FormEvent) {
    event.preventDefault();
    setSearching(true);
    setMessage(null);
    try {
      const params = new URLSearchParams({ limit: "24" });
      if (query.trim()) params.set("q", query.trim());
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1"}/films?${params}`);
      if (!response.ok) throw new Error();
      const results: Film[] = await response.json();
      setFilms(results);
      if (!results.length) setMessage("No films match that title. Try a broader title search.");
    } catch {
      setMessage("Search could not reach the catalog. Please try again.");
    } finally {
      setSearching(false);
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
          <h1>Find the connections<br />behind a film.</h1>
          <p className="intro">Browse an evidence-backed film graph: credits, genres, eras and explainable connections—not scraped creative content.</p>
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

      <section className="catalog">
        <div className="catalog-heading">
          <div><p className="eyebrow">Catalog</p><h2>Explore films</h2></div>
          <form onSubmit={search} className="search"><input aria-label="Search films" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search by title" /><button disabled={searching}>{searching ? "Searching" : "Search"}</button></form>
        </div>
        {message && <p className="notice">{message}</p>}
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
