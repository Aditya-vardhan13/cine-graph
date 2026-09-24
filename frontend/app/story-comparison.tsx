"use client";

import { useEffect, useRef, useState } from "react";
import { ResearchFilm, StoryComparison, StoryComparisonEvidence, year } from "../lib/api";

const EXAMPLE_QUESTION = "How do these films turn the same idea into different character choices and consequences?";

export function StoryComparisonWorkbench() {
  const [first, setFirst] = useState<ResearchFilm | null>(null);
  const [second, setSecond] = useState<ResearchFilm | null>(null);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<ResearchFilm[]>([]);
  const [searching, setSearching] = useState(false);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<StoryComparison | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchedQuery, setSearchedQuery] = useState("");
  const [searchError, setSearchError] = useState<string | null>(null);
  const comparisonRequest = useRef<AbortController | null>(null);

  useEffect(() => () => { comparisonRequest.current?.abort(); }, []);

  function invalidateComparison() {
    comparisonRequest.current?.abort();
    comparisonRequest.current = null;
    setResult(null);
    setLoading(false);
    setError(null);
  }

  function changeQuestion(value: string) {
    invalidateComparison();
    setQuestion(value);
  }

  useEffect(() => {
    const normalized = query.trim();
    setSuggestions([]);
    setSearchError(null);
    setSearchedQuery("");
    setSearching(false);
    if (normalized.length < 2) return;
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await fetch(`/api/v1/research/films?q=${encodeURIComponent(normalized)}&limit=7`, {signal: controller.signal});
        if (!response.ok) throw new Error();
        const films: ResearchFilm[] = await response.json();
        if (active) {
          setSuggestions(films.filter((film) => film.entity_id !== first?.entity_id && film.entity_id !== second?.entity_id));
          setSearchedQuery(normalized);
        }
      } catch {
        if (active) setSearchError("Film search is unavailable. Please try again.");
      } finally {
        if (active) setSearching(false);
      }
    }, 180);
    return () => { active = false; window.clearTimeout(timer); controller.abort(); };
  }, [first?.entity_id, query, second?.entity_id]);

  function chooseFilm(film: ResearchFilm) {
    invalidateComparison();
    if (!first) setFirst(film);
    else if (!second) setSecond(film);
    else setSecond(film);
    setQuery("");
    setSuggestions([]);
    setResult(null);
    setError(null);
  }

  async function compare() {
    if (!first || !second || question.trim().length < 12) return;
    invalidateComparison();
    const controller = new AbortController();
    comparisonRequest.current = controller;
    const deadline = window.setTimeout(() => controller.abort(), 20000);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/api/v1/comparisons/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_entity_id: first.entity_id, second_entity_id: second.entity_id, question: question.trim() }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error();
      const payload: StoryComparison = await response.json();
      if (comparisonRequest.current === controller) setResult(payload);
    } catch {
      if (comparisonRequest.current === controller) setError(controller.signal.aborted
        ? "The comparison took too long. Please try again."
        : "The evidence comparison could not be completed. Please try again.");
    } finally {
      window.clearTimeout(deadline);
      if (comparisonRequest.current === controller) {
        comparisonRequest.current = null;
        setLoading(false);
      }
    }
  }

  return <>
    <section id="compare" className="story-workbench">
      <div className="workbench-copy">
        <p className="eyebrow">Writer&apos;s comparison desk</p>
        <h2>Ask a better question than “are these similar?”</h2>
        <p>Place two films beside one writing problem. CineGraph retrieves plot, character, craft and reception evidence for both without turning similarity into a fact.</p>
        <div className="comparison-examples">
          <span>Try asking</span>
          <button onClick={() => changeQuestion("How does each film make an artificial companion expose human loneliness?")}>Human–AI intimacy</button>
          <button onClick={() => changeQuestion("How does a reluctant heir return to power, and what does that power cost?")}>The returning heir</button>
          <button onClick={() => changeQuestion("How does each antagonist force the hero to compromise a moral code?")}>Moral compromise</button>
        </div>
      </div>
      <div className="workbench-controls">
        <div className="comparison-slots">
          <FilmChoice label="First film" film={first} onClear={() => { invalidateComparison(); setFirst(null); }} />
          <span>×</span>
          <FilmChoice label="Second film" film={second} onClear={() => { invalidateComparison(); setSecond(null); }} />
        </div>
        <div className="live-search compare-search">
          <span className="search-glyph">⌕</span>
          <input aria-label="Search comparison films" autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={!first ? "Find the first film…" : "Find or replace the second film…"} />
          <span className="search-state">{searching ? "Searching" : "Live"}</span>
          {(suggestions.length > 0 || searchError || (searchedQuery === query.trim() && query.trim().length >= 2 && !searching)) && <div className="suggestions">
            {searchError ? <p role="status">{searchError}</p> : suggestions.length ? suggestions.map((film) => <button key={film.entity_id} onClick={() => chooseFilm(film)}><span><b>{film.title}</b><small>{film.release_year ?? year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Genre unavailable"}</small></span><i>select ↗</i></button>) : <p role="status">No other title matches “{query.trim()}”.</p>}
          </div>}
        </div>
        <label className="writer-question-input">
          <span>Your writing question</span>
          <textarea value={question} onChange={(event) => changeQuestion(event.target.value)} maxLength={400} placeholder={EXAMPLE_QUESTION} />
          <small>{question.trim().length}/400 · minimum 12 characters</small>
        </label>
        <button className="compare-button" disabled={!first || !second || question.trim().length < 12 || loading} onClick={compare}>{loading ? "Retrieving both films…" : "Build evidence comparison"}</button>
        {error && <p className="notice">{error}</p>}
      </div>
    </section>
    {result && <ComparisonResult result={result} />}
  </>;
}

function FilmChoice({ label, film, onClear }: { label: string; film: ResearchFilm | null; onClear: () => void }) {
  return <div className={film ? "film-slot selected" : "film-slot"}>{film ? <><span>{label}</span><b>{film.title}</b><small title={film.release_basis ? "Earliest recorded release" : undefined}>{film.release_year ?? year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Genre unavailable"}</small><button aria-label={`Remove ${film.title}`} onClick={onClear}>×</button></> : <><span>{label}</span><b>Choose a film</b><small>Use live search below</small></>}</div>;
}

function ComparisonResult({ result }: { result: StoryComparison }) {
  return <section className="story-comparison-result">
    <header>
      <div><p className="eyebrow">Evidence comparison</p><h2>{result.first.title} <i>×</i> {result.second.title}</h2><p className="comparison-question">“{result.question}”</p></div>
      <div className={result.degraded ? "retrieval-badge degraded" : "retrieval-badge"}><span>{result.retrieval_method} retrieval</span><small>{result.summary}</small></div>
    </header>
    {result.fallback_reason && <p className="fallback-note">{result.fallback_reason}</p>}
    <div className="comparison-column-headings"><span>{result.first.title}</span><i>Lens</i><span>{result.second.title}</span></div>
    <div className="comparison-lenses">{result.lenses.map((lens) => <article key={lens.identifier} className="comparison-lens">
      <EvidenceCard evidence={lens.first_evidence} filmTitle={result.first.title} />
      <div className="lens-center"><span>{lens.label}</span><p>{lens.writer_prompt}</p></div>
      <EvidenceCard evidence={lens.second_evidence} filmTitle={result.second.title} />
    </article>)}</div>
    <footer>{result.caution}</footer>
  </section>;
}

function EvidenceCard({ evidence, filmTitle }: { evidence: StoryComparisonEvidence | null; filmTitle: string }) {
  if (!evidence) return <div className="evidence-card empty-evidence"><span>No additional passage</span><p>No distinct passage was available for {filmTitle} under this lens. Related evidence may already appear above.</p></div>;
  return <div className="evidence-card"><div><span>{evidence.section_title}</span><small>{evidence.matched_by.join(" + ")}</small></div><p>{evidence.excerpt}</p><a href={evidence.source_url} target="_blank">Source · {evidence.source_license} ↗</a></div>;
}
