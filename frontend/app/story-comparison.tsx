"use client";

import { useEffect, useRef, useState } from "react";
import { ResearchDiscovery, ResearchFilm, StoryComparison, StoryComparisonEvidence, year } from "../lib/api";
import { parseWriterDecisionArchive, PinnedEvidence, renderWriterDecisionsMarkdown, WriterDecision } from "../lib/writer-study-export";

const EXAMPLE_QUESTION = "How do these films turn the same idea into different character choices and consequences?";
const NOTE_STORAGE_KEY = "cinegraph-writer-decisions-v1";

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
  const [discovery, setDiscovery] = useState<ResearchDiscovery | null>(null);
  const [discovering, setDiscovering] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string | null>(null);
  const comparisonRequest = useRef<AbortController | null>(null);
  const discoveryRequest = useRef<AbortController | null>(null);

  useEffect(() => () => { comparisonRequest.current?.abort(); discoveryRequest.current?.abort(); }, []);

  function invalidateComparison() {
    comparisonRequest.current?.abort();
    comparisonRequest.current = null;
    setResult(null);
    setLoading(false);
    setError(null);
  }

  function changeQuestion(value: string) {
    invalidateComparison();
    discoveryRequest.current?.abort();
    discoveryRequest.current = null;
    setDiscovery(null);
    setDiscovering(false);
    setDiscoveryError(null);
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

  async function discoverFilms() {
    if (question.trim().length < 12) return;
    discoveryRequest.current?.abort();
    const controller = new AbortController();
    discoveryRequest.current = controller;
    const deadline = window.setTimeout(() => controller.abort(), 20000);
    setDiscovering(true);
    setDiscoveryError(null);
    setDiscovery(null);
    try {
      const response = await fetch("/api/v1/research/discover", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question.trim(),
          exclude_entity_ids: [first?.entity_id, second?.entity_id].filter(Boolean),
          limit: 6,
        }),
        signal: controller.signal,
      });
      if (!response.ok) throw new Error();
      const payload: ResearchDiscovery = await response.json();
      if (discoveryRequest.current === controller) setDiscovery(payload);
    } catch {
      if (discoveryRequest.current === controller)
        setDiscoveryError(controller.signal.aborted
          ? "Film discovery took too long. Try a more specific question or search by title."
          : "Film discovery is unavailable. You can still search by title.");
    } finally {
      window.clearTimeout(deadline);
      if (discoveryRequest.current === controller) {
        discoveryRequest.current = null;
        setDiscovering(false);
      }
    }
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
        <p>Start with a writing problem or a film. Find source-linked films to study, then compare how two of them handle your question.</p>
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
          <input id="comparison-film-search" aria-label="Search comparison films" autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={!first ? "Find the first film…" : "Find or replace the second film…"} />
          <span className="search-state">{searching ? "Searching" : "Live"}</span>
          {(suggestions.length > 0 || searchError || (searchedQuery === query.trim() && query.trim().length >= 2 && !searching)) && <div className="suggestions">
            {searchError ? <p role="status">{searchError}</p> : suggestions.length ? suggestions.map((film) => <button key={film.entity_id} onClick={() => chooseFilm(film)}><span><b>{film.title}</b><small>{film.release_year ?? year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Genre unavailable"}</small></span><i>select ↗</i></button>) : <p role="status">No other title matches “{query.trim()}”.</p>}
          </div>}
        </div>
        <label className="writer-question-input">
          <span>Your writing question</span>
          <textarea id="writer-question" value={question} onChange={(event) => changeQuestion(event.target.value)} maxLength={400} placeholder={EXAMPLE_QUESTION} />
          <small>{question.trim().length}/400 · minimum 12 characters</small>
        </label>
        <button className="discovery-button" disabled={question.trim().length < 12 || discovering} onClick={discoverFilms}>{discovering ? "Finding film leads…" : "Find films for this question"}</button>
        <button className="compare-button" disabled={!first || !second || question.trim().length < 12 || loading} onClick={compare}>{loading ? "Retrieving both films…" : "Build evidence comparison"}</button>
        {discoveryError && <p className="notice">{discoveryError}</p>}
        {error && <p className="notice">{error}</p>}
      </div>
    </section>
    {discovery && <section className="discovery-results" aria-live="polite">
      <div><p className="eyebrow">Question-first film leads</p><h2>Candidate film leads</h2><p>{discovery.reason} A passage match does not establish that the film fits every part of your question.</p>{discovery.degraded && <small>Semantic search was unavailable; these leads use exact-term retrieval.</small>}</div>
      {discovery.leads.some((lead) => lead.film.entity_id !== first?.entity_id && lead.film.entity_id !== second?.entity_id) ? <div className="discovery-grid">{discovery.leads.filter((lead) => lead.film.entity_id !== first?.entity_id && lead.film.entity_id !== second?.entity_id).map((lead) => <article key={lead.film.entity_id}>
        <h3>{lead.film.title}</h3><small>{lead.film.release_year ?? year(lead.film.release_date)} · {lead.section_title}</small>
        <p>{lead.excerpt.slice(0, 340)}{lead.excerpt.length > 340 ? "…" : ""}</p>
        <a href={lead.source_url} target="_blank" rel="noopener noreferrer">Inspect source · {lead.source_license} · revision {lead.source_revision || "unavailable"} ↗</a>
        <button onClick={() => chooseFilm(lead.film)}>Add to comparison</button>
      </article>)}</div> : <p>{discovery.method === "not_run" ? "No film leads were suggested without the required evidence." : "No attributable film leads were found for this question. Try a more specific dramatic situation."}</p>}
    </section>}
    {result && <ComparisonResult key={`${result.first.entity_id}:${result.second.entity_id}:${result.question}`} result={result} />}
  </>;
}

function FilmChoice({ label, film, onClear }: { label: string; film: ResearchFilm | null; onClear: () => void }) {
  return <div className={film ? "film-slot selected" : "film-slot"}>{film ? <><span>{label}</span><b>{film.title}</b><small title={film.release_basis ? "Earliest recorded release" : undefined}>{film.release_year ?? year(film.release_date)} · {film.genres.slice(0, 2).join(", ") || "Genre unavailable"}</small><button aria-label={`Remove ${film.title}`} onClick={onClear}>×</button></> : <><span>{label}</span><b>Choose a film</b><small>Use live search below</small></>}</div>;
}

function ComparisonResult({ result }: { result: StoryComparison }) {
  const [pinned, setPinned] = useState<PinnedEvidence[]>([]);
  useEffect(() => { setPinned([]); }, [result]);

  function toggleEvidence(filmEntityId: string, evidence: StoryComparisonEvidence) {
    setPinned((current) => current.some((item) => item.chunk_id === evidence.chunk_id)
      ? current.filter((item) => item.chunk_id !== evidence.chunk_id)
      : [...current, {
        chunk_id: evidence.chunk_id,
        film_entity_id: filmEntityId,
        section_title: evidence.section_title,
        section_locator: evidence.section_locator,
        passage_preview: evidence.excerpt.replace(/\s+/g, " ").slice(0, 240),
        source_url: evidence.source_url,
        source_revision: evidence.source_revision,
        source_license: evidence.source_license,
      }]);
  }

  if (result.answerability_status === "insufficient_evidence") return <section className="story-comparison-result insufficient-evidence" aria-live="polite">
    <p className="eyebrow">Insufficient evidence</p><h2>{result.summary}</h2>
    <p>{result.answerability_reason}</p><small>{result.caution}</small>
    <div className="evidence-recovery"><a href="#writer-question">Refine the question ↑</a><a href="#comparison-film-search">Try another film ↑</a></div>
  </section>;
  const focus = result.lenses.find((lens) => lens.identifier === "central_question" && lens.first_evidence && lens.second_evidence)
    || result.lenses.find((lens) => lens.first_evidence && lens.second_evidence);
  const furtherContext = result.lenses.filter((lens) => lens !== focus);
  return <section className="story-comparison-result">
    <header>
      <div><p className="eyebrow">Evidence comparison</p><h2>{result.first.title} <i>×</i> {result.second.title}</h2><p className="comparison-question">“{result.question}”</p></div>
      <div className={result.degraded ? "retrieval-badge degraded" : "retrieval-badge"}><span>{result.retrieval_method} retrieval</span><small>{result.summary}</small></div>
    </header>
    {result.fallback_reason && <p className="fallback-note">{result.fallback_reason}</p>}
    <div className="comparison-column-headings"><span>{result.first.title}</span><i>Question evidence</i><span>{result.second.title}</span></div>
    {focus && <div className="comparison-lenses"><article className="comparison-lens focus-lens">
      <EvidenceChoices evidence={focus.first_evidence} options={focus.first_options} filmTitle={result.first.title} pinned={pinned} onPin={(evidence) => toggleEvidence(result.first.entity_id, evidence)} />
      <div className="lens-center"><span>{focus.label}</span><p>{focus.writer_prompt}</p></div>
      <EvidenceChoices evidence={focus.second_evidence} options={focus.second_options} filmTitle={result.second.title} pinned={pinned} onPin={(evidence) => toggleEvidence(result.second.entity_id, evidence)} />
    </article></div>}
    {furtherContext.length > 0 && <details className="additional-context"><summary>Additional source context ({furtherContext.length} lenses) · may not answer your question</summary><div className="comparison-lenses">{furtherContext.map((lens) => <article key={lens.identifier} className="comparison-lens">
      <EvidenceCard evidence={lens.first_evidence} filmTitle={result.first.title} pinned={pinned.some((item) => item.chunk_id === lens.first_evidence?.chunk_id)} onPin={() => { if (lens.first_evidence) toggleEvidence(result.first.entity_id, lens.first_evidence); }} />
      <div className="lens-center"><span>{lens.label}</span><p>{lens.writer_prompt}</p></div>
      <EvidenceCard evidence={lens.second_evidence} filmTitle={result.second.title} pinned={pinned.some((item) => item.chunk_id === lens.second_evidence?.chunk_id)} onPin={() => { if (lens.second_evidence) toggleEvidence(result.second.entity_id, lens.second_evidence); }} />
    </article>)}</div></details>}
    <footer>{result.caution}</footer>
    <WriterDecisionPad result={result} pinned={pinned} />
  </section>;
}

function EvidenceChoices({ evidence, options, filmTitle, pinned, onPin }: {
  evidence: StoryComparisonEvidence | null;
  options: StoryComparisonEvidence[];
  filmTitle: string;
  pinned: PinnedEvidence[];
  onPin: (evidence: StoryComparisonEvidence) => void;
}) {
  const [position, setPosition] = useState(0);
  const choices = options?.length ? options : evidence ? [evidence] : [];
  const selected = choices[position] || choices[0] || null;
  return <div className="evidence-choice">
    <EvidenceCard evidence={selected} filmTitle={filmTitle} pinned={Boolean(selected && pinned.some((item) => item.chunk_id === selected.chunk_id))} onPin={() => { if (selected) onPin(selected); }} />
    {choices.length > 1 && <nav className="evidence-choice-nav" aria-label={`Source passages for ${filmTitle}`}>
      <span>Passage {position + 1} of {choices.length} · ranked lead, not a verdict</span>
      <div><button aria-label={`Previous passage for ${filmTitle}`} disabled={position === 0} onClick={() => setPosition(position - 1)}>← Previous</button><button aria-label={`Next passage for ${filmTitle}`} disabled={position === choices.length - 1} onClick={() => setPosition(position + 1)}>Next →</button></div>
    </nav>}
  </div>;
}

function WriterDecisionPad({ result, pinned }: { result: StoryComparison; pinned: PinnedEvidence[] }) {
  const [firstMechanism, setFirstMechanism] = useState("");
  const [secondMechanism, setSecondMechanism] = useState("");
  const [contrast, setContrast] = useState("");
  const [draft, setDraft] = useState("");
  const [notes, setNotes] = useState<WriterDecision[]>([]);
  const [storageError, setStorageError] = useState<string | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);

  useEffect(() => {
    try {
      setNotes(parseWriterDecisionArchive(JSON.parse(window.localStorage.getItem(NOTE_STORAGE_KEY) || "[]")));
    } catch {
      setStorageError("Saved notes could not be loaded from this browser.");
    }
  }, []);

  function save() {
    const decision = draft.trim();
    if (!decision || !firstMechanism.trim() || !secondMechanism.trim() || !contrast.trim() ||
      !pinned.some((item) => item.film_entity_id === result.first.entity_id) ||
      !pinned.some((item) => item.film_entity_id === result.second.entity_id)) return;
    const sources = Array.from(new Set(pinned.map((item) => item.source_url)));
    const next: WriterDecision[] = [{
      id: window.crypto.randomUUID(), created_at: new Date().toISOString(),
      question: result.question,
      films: [result.first, result.second].map((film) => ({ entity_id: film.entity_id, title: film.title })),
      version: 3, first_mechanism: firstMechanism.trim(), second_mechanism: secondMechanism.trim(),
      contrast: contrast.trim(), decision, sources, evidence: pinned,
      preprocessing_run_id: result.preprocessing_run_id, index_run_id: result.index_run_id,
    }, ...notes];
    try {
      window.localStorage.setItem(NOTE_STORAGE_KEY, JSON.stringify(next));
      setNotes(next);
      setFirstMechanism("");
      setSecondMechanism("");
      setContrast("");
      setDraft("");
      setStorageError(null);
    } catch {
      setStorageError("This browser could not save the note. Copy your text before leaving.");
    }
  }

  function downloadNotes(contents: string, type: string, filename: string) {
    const url = URL.createObjectURL(new Blob([contents], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function importNotes(file: File | undefined) {
    if (!file) return;
    setImportMessage(null);
    try {
      if (file.size > 5_000_000) throw new Error("The archive is too large (5 MB maximum).");
      const incoming = parseWriterDecisionArchive(JSON.parse(await file.text()));
      const existingIds = new Set(incoming.map((note) => note.id));
      const merged = [...incoming, ...notes.filter((note) => !existingIds.has(note.id))];
      if (merged.length > 1000) throw new Error("The combined archive exceeds 1,000 studies. Export a backup first.");
      window.localStorage.setItem(NOTE_STORAGE_KEY, JSON.stringify(merged));
      setNotes(merged);
      setStorageError(null);
      setImportMessage(`${incoming.length} stud${incoming.length === 1 ? "y" : "ies"} restored from this file.`);
    } catch (error) {
      setStorageError(error instanceof Error ? error.message : "This study archive could not be imported.");
    }
  }

  const current = notes.filter((note) => note.question === result.question &&
    note.films[0]?.entity_id === result.first.entity_id && note.films[1]?.entity_id === result.second.entity_id);
  const firstPins = pinned.filter((item) => item.film_entity_id === result.first.entity_id);
  const secondPins = pinned.filter((item) => item.film_entity_id === result.second.entity_id);
  const canSave = Boolean(firstMechanism.trim() && secondMechanism.trim() && contrast.trim() && draft.trim() && firstPins.length && secondPins.length);
  return <div className="writer-decision-pad">
    <div><p className="eyebrow">Your study canvas</p><h3>What would you try differently?</h3><p>Pin at least one source passage for each film, then write your own reading. These fields are your interpretation, not CineGraph facts.</p></div>
    <div className="pinned-source-count"><span>{result.first.title}: {firstPins.length} pinned</span><span>{result.second.title}: {secondPins.length} pinned</span></div>
    <div className="mechanism-fields">
      <label><span>How {result.first.title} handles it</span><textarea value={firstMechanism} onChange={(event) => setFirstMechanism(event.target.value)} maxLength={1200} placeholder="What pressure, choice and consequence do you see?" /></label>
      <label><span>How {result.second.title} handles it</span><textarea value={secondMechanism} onChange={(event) => setSecondMechanism(event.target.value)} maxLength={1200} placeholder="Where does this film take another route?" /></label>
    </div>
    <label className="decision-field"><span>The meaningful difference</span><textarea value={contrast} onChange={(event) => setContrast(event.target.value)} maxLength={1200} placeholder="The two films share a problem, but differ in…" /></label>
    <label className="decision-field"><span>My original move</span><textarea aria-label="Your creative decision" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={2000} placeholder="For my story, I would…" /></label>
    <div className="decision-actions"><button disabled={!canSave} onClick={save}>Save this study</button><small>Stored only in this browser. Export a copy to keep it.</small>{notes.length > 0 && <><button className="export-notes" onClick={() => downloadNotes(renderWriterDecisionsMarkdown(notes), "text/markdown", "cinegraph-writer-studies.md")}>Export readable notes</button><button className="export-notes" onClick={() => downloadNotes(JSON.stringify(notes, null, 2), "application/json", "cinegraph-writer-decisions.json")}>Export JSON</button></>}<label className="import-notes">Restore JSON<input aria-label="Restore writer studies from JSON" type="file" accept="application/json,.json" onChange={(event) => { void importNotes(event.target.files?.[0]); event.target.value = ""; }} /></label></div>
    {storageError && <p role="alert">{storageError}</p>}
    {importMessage && <p role="status">{importMessage}</p>}
    {current.length > 0 && <div className="saved-decisions"><h4>Saved for this comparison</h4>{current.map((note) => <article key={note.id}>
      {note.first_mechanism && <p><b>{result.first.title}:</b> {note.first_mechanism}</p>}
      {note.second_mechanism && <p><b>{result.second.title}:</b> {note.second_mechanism}</p>}
      {note.contrast && <p><b>Difference:</b> {note.contrast}</p>}
      <p><b>My move:</b> {note.decision}</p>
      <small>{new Date(note.created_at).toLocaleString()} · {(note.evidence || []).length} pinned passage{(note.evidence || []).length === 1 ? "" : "s"}</small>
      {note.evidence && <details><summary>Inspect pinned sources</summary>{note.evidence.map((item) => <div key={item.chunk_id}><a href={item.source_url} target="_blank" rel="noopener noreferrer">{item.section_title} · {item.source_revision || "source revision unavailable"} ↗</a>{item.passage_preview && <p>{item.passage_preview}</p>}</div>)}</details>}
    </article>)}</div>}
  </div>;
}

function EvidenceCard({ evidence, filmTitle, pinned, onPin }: { evidence: StoryComparisonEvidence | null; filmTitle: string; pinned: boolean; onPin: () => void }) {
  if (!evidence) return <div className="evidence-card empty-evidence"><span>No additional passage</span><p>No distinct passage was available for {filmTitle} under this lens. Related evidence may already appear above.</p></div>;
  return <div className="evidence-card"><div><span>{evidence.section_title}</span><small>Source passage</small></div><p>{evidence.excerpt}</p><div className="evidence-actions"><a href={evidence.source_url} target="_blank" rel="noopener noreferrer">Source · {evidence.source_license} · revision {evidence.source_revision || "unavailable"} ↗</a><button aria-pressed={pinned} onClick={onPin}>{pinned ? "Pinned to study ✓" : "Pin as evidence +"}</button></div></div>;
}
