"use client";

import { useEffect, useState } from "react";
import { ResearchFilm, year } from "../lib/api";

export function ResearchCatalogSearch({ count }: { count: number | undefined }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ResearchFilm[]>([]);
  const [searched, setSearched] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const normalized = query.trim();
    setResults([]);
    setSearched("");
    setError(false);
    setLoading(false);
    if (normalized.length < 2) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const response = await fetch(`/api/v1/research/films?q=${encodeURIComponent(normalized)}&limit=12`, { signal: controller.signal });
        if (!response.ok) throw new Error();
        const films: ResearchFilm[] = await response.json();
        if (!controller.signal.aborted) { setResults(films); setSearched(normalized); }
      } catch {
        if (!controller.signal.aborted) setError(true);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  return <div className="research-catalog-search">
    <label htmlFor="research-catalog-query">Search the {count?.toLocaleString("en-IN") || "current"}-film writer library</label>
    <div className="research-catalog-input"><span aria-hidden="true">⌕</span><input id="research-catalog-query" value={query} onChange={(event) => setQuery(event.target.value)} autoComplete="off" placeholder="Search a film to study…" /><small>{loading ? "Searching" : "Live"}</small></div>
    {error && <p role="status">The writer library could not be searched. Try again.</p>}
    {searched === query.trim() && !loading && !error && <div className="research-catalog-results" aria-live="polite">
      {results.length ? results.map((film) => <a key={film.entity_id} href={`/?study=${film.entity_id}#compare`}><span><strong>{film.title}</strong><small>{film.release_year ?? year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Genre not sourced"}</small></span><i>Study ↗</i></a>) : <p>No research film matches “{searched}”. Try fewer words.</p>}
    </div>}
  </div>;
}
