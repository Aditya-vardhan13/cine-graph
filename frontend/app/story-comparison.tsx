"use client";

import { useEffect, useState } from "react";
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

  useEffect(() => {
    const normalized = query.trim();
    if (normalized.length < 2) { setSuggestions([]); return; }
    let active = true;
    const timer = window.setTimeout(async () => {
      setSearching(true);
      try {
        const response = await fetch(`/api/v1/research/films?q=${encodeURIComponent(normalized)}&limit=7`);
        if (!response.ok) throw new Error();
        const films: ResearchFilm[] = await response.json();
        if (active) setSuggestions(films.filter((film) => film.entity_id !== first?.entity_id && film.entity_id !== second?.entity_id));
      } catch {
        if (active) setError("Film search is unavailable. Check that the API is running.");
      } finally {
        if (active) setSearching(false);
      }
    }, 180);
    return () => { active = false; window.clearTimeout(timer); };
  }, [first?.entity_id, query, second?.entity_id]);

  function chooseFilm(film: ResearchFilm) {
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
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch("/api/v1/comparisons/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ first_entity_id: first.entity_id, second_entity_id: second.entity_id, question: question.trim() }),
      });
      if (!response.ok) throw new Error();
      setResult(await response.json());
    } catch {
      setError("The evidence comparison could not be completed. Check the local API and try again.");
    } finally {
      setLoading(false);
    }
  }

  return <>
    <section className="story-workbench">
      <div className="workbench-copy">
        <p className="eyebrow">Writer&apos;s comparison desk</p>
        <h2>Ask a better question than “are these similar?”</h2>
        <p>Place two films beside one writing problem. CineGraph retrieves plot, character, craft and reception evidence for both without turning similarity into a fact.</p>
        <div className="comparison-examples">
          <span>Try asking</span>
          <button onClick={() => setQuestion("How does each film make an artificial companion expose human loneliness?")}>Human–AI intimacy</button>
          <button onClick={() => setQuestion("How does a reluctant heir return to power, and what does that power cost?")}>The returning heir</button>
          <button onClick={() => setQuestion("How does each antagonist force the hero to compromise a moral code?")}>Moral compromise</button>
        </div>
      </div>
      <div className="workbench-controls">
        <div className="comparison-slots">
          <FilmChoice label="First film" film={first} onClear={() => { setFirst(null); setResult(null); }} />
          <span>×</span>
          <FilmChoice label="Second film" film={second} onClear={() => { setSecond(null); setResult(null); }} />
        </div>
        <div className="live-search compare-search">
          <span className="search-glyph">⌕</span>
          <input aria-label="Search comparison films" autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={!first ? "Find the first film…" : "Find or replace the second film…"} />
          <span className="search-state">{searching ? "Searching" : "Live"}</span>
          {suggestions.length > 0 && <div className="suggestions">{suggestions.map((film) => <button key={film.entity_id} onClick={() => chooseFilm(film)}><span><b>{film.title}</b><small>{year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Narrative corpus"}</small></span><i>select ↗</i></button>)}</div>}
        </div>
        <label className="writer-question-input">
          <span>Your writing question</span>
          <textarea value={question} onChange={(event) => { setQuestion(event.target.value); setResult(null); }} maxLength={400} placeholder={EXAMPLE_QUESTION} />
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
  return <div className={film ? "film-slot selected" : "film-slot"}>{film ? <><span>{label}</span><b>{film.title}</b><small>{year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Narrative record"}</small><button aria-label={`Remove ${film.title}`} onClick={onClear}>×</button></> : <><span>{label}</span><b>Choose a film</b><small>Use live search below</small></>}</div>;
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
  if (!evidence) return <div className="evidence-card empty-evidence"><span>No matching passage</span><p>The retained corpus did not return evidence for {filmTitle} under this lens.</p></div>;
  return <div className="evidence-card"><div><span>{evidence.section_title}</span><small>{evidence.matched_by.join(" + ")}</small></div><p>{evidence.excerpt}</p><a href={evidence.source_url} target="_blank">Source · {evidence.source_license} ↗</a></div>;
}
