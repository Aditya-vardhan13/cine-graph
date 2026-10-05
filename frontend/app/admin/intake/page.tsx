"use client";

import { useEffect, useState } from "react";
import "./intake.css";

type Candidate = { imdb_id: string; title: string; year: number | null };
type IntakeJob = Candidate & {
  id: string; status: string; stage: string; attempts: number;
  review_reason: string | null; film_entity_id: string | null;
};

const endpoint = "/api/admin/intake";

function movieId(value: string): string | null {
  const trimmed = value.trim();
  if (/^tt\d{7,10}$/.test(trimmed)) return trimmed;
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "https:" || !["imdb.com", "www.imdb.com", "m.imdb.com"].includes(url.hostname)) return null;
    return url.pathname.match(/^\/title\/(tt\d{7,10})\/?$/)?.[1] ?? null;
  } catch { return null; }
}

export default function IntakePage() {
  const [key, setKey] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate[]>([]);
  const [jobs, setJobs] = useState<IntakeJob[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (key.length < 24 || query.trim().length < 2 || movieId(query)) { setResults([]); return; }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const response = await fetch(`${endpoint}/suggest?q=${encodeURIComponent(query.trim())}`, {
          headers: { authorization: `Bearer ${key}` }, signal: controller.signal,
        });
        const body = await response.json();
        if (!response.ok) { setMessage(body.detail ?? "Search unavailable"); setResults([]); return; }
        setResults(body.results ?? []);
        setMessage("");
      } catch { if (!controller.signal.aborted) setMessage("Search unavailable"); }
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [key, query]);

  useEffect(() => {
    if (key.length < 24) { setJobs([]); return; }
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch(`${endpoint}/jobs`, {
          headers: { authorization: `Bearer ${key}` }, cache: "no-store",
        });
        const body = await response.json();
        if (active && response.ok) setJobs(body.jobs ?? []);
        if (active && !response.ok) setMessage(body.detail ?? "Cannot load intake jobs");
      } catch { if (active) setMessage("Cannot reach the local API"); }
    };
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => { active = false; clearInterval(timer); };
  }, [key]);

  function add(candidate: Candidate) {
    setSelected(current => current.some(item => item.imdb_id === candidate.imdb_id)
      ? current : [...current, candidate]);
    setQuery("");
    setResults([]);
    setMessage("");
  }

  function addTypedId() {
    const id = movieId(query);
    if (!id) { setMessage("Paste an HTTPS IMDb film URL or select a title from the list."); return; }
    add({ imdb_id: id, title: id, year: null });
  }

  async function submit() {
    if (!selected.length || busy) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`${endpoint}/jobs`, {
        method: "POST", headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
        body: JSON.stringify({ films: selected.map(item => item.imdb_id) }),
      });
      const body = await response.json();
      if (!response.ok) { setMessage(body.detail ?? "Could not submit films"); return; }
      setJobs(current => [...body.jobs, ...current.filter(job => !body.jobs.some((next: IntakeJob) => next.id === job.id))]);
      setSelected([]);
      setMessage(`${body.jobs.length} film${body.jobs.length === 1 ? "" : "s"} queued or already tracked.`);
    } catch { setMessage("Could not reach the local API"); }
    finally { setBusy(false); }
  }

  async function retry(job: IntakeJob) {
    const response = await fetch(`${endpoint}/jobs/${job.id}/retry`, {
      method: "POST", headers: { authorization: `Bearer ${key}` },
    });
    const body = await response.json();
    if (!response.ok) { setMessage(body.detail ?? "Retry failed"); return; }
    setJobs(current => current.map(item => item.id === job.id ? body : item));
  }

  return <main className="intake-shell">
    <div className="intake-head"><span className="intake-kicker">CineGraph · Local operator desk</span>
      <h1>Add films to the research corpus</h1>
      <p>Find exact titles in the local IMDb index, select several, and submit once. Each film moves through attributable source ingestion; uncertain matches stop for review.</p>
    </div>
    <section className="intake-panel" aria-label="Operator access">
      <label htmlFor="intake-key">Operator key</label>
      <input id="intake-key" type="password" value={key} onChange={event => setKey(event.target.value)}
             autoComplete="off" placeholder="Local admin key" />
      <p>This local pilot uses an operator key. Email-verified sign-in is not enabled yet. The key stays in this tab and is not saved.</p>
    </section>
    <div className="intake-grid">
      <section className="intake-panel">
        <h2>1 · Find and select</h2>
        <label htmlFor="movie-search">Film title or IMDb URL</label>
        <div className="intake-search-row"><input id="movie-search" value={query} onChange={event => setQuery(event.target.value)}
          placeholder="Try The Dark Knight, RRR, or an IMDb URL" disabled={key.length < 24} />
          <button type="button" onClick={addTypedId} disabled={key.length < 24 || !query.trim()}>Add URL</button></div>
        {results.length > 0 && <div className="intake-suggestions" role="listbox" aria-label="Matching films">
          {results.map(result => <button key={result.imdb_id} type="button" role="option" aria-selected="false"
            onClick={() => add(result)}><span>{result.title}<small>{result.year ?? "Year unknown"}</small></span><code>{result.imdb_id}</code></button>)}
        </div>}
        <div className="intake-selected"><h3>Selected · {selected.length}/20</h3>
          {selected.length === 0 ? <p>Nothing selected yet.</p> : selected.map(item =>
            <div className="intake-chip" key={item.imdb_id}><span>{item.title} {item.year ? `(${item.year})` : ""}<small>{item.imdb_id}</small></span>
              <button type="button" aria-label={`Remove ${item.title}`} onClick={() => setSelected(current => current.filter(row => row.imdb_id !== item.imdb_id))}>×</button></div>)}
        </div>
        <button className="intake-submit" type="button" disabled={!selected.length || busy || selected.length > 20}
          onClick={submit}>{busy ? "Submitting…" : `Submit ${selected.length || "selected"} film${selected.length === 1 ? "" : "s"}`}</button>
        {message && <p className="intake-message" role="status">{message}</p>}
      </section>
      <section className="intake-panel">
        <h2>2 · Watch the pipeline</h2>
        <p>Jobs refresh every five seconds. “Needs review” flags an identity conflict; “ready with gaps” lists missing source material, including a full plot when unavailable.</p>
        <div className="intake-jobs">{jobs.length === 0 ? <p>No submitted films yet.</p> : jobs.map(job =>
          <article className="intake-job" key={job.id}><div><strong>{job.title}</strong><small>{job.year ?? "Year unknown"} · {job.imdb_id}</small></div>
            <span className={`intake-status intake-status-${job.status}`}>{job.status.replaceAll("_", " ")}</span>
            <p>Stage: {job.stage.replaceAll("_", " ")}{job.review_reason ? ` · ${job.review_reason}` : ""}</p>
            {(job.status === "failed" || job.status === "needs_review") && <button type="button" onClick={() => retry(job)}>Retry after review</button>}
          </article>)}
        </div>
      </section>
    </div>
  </main>;
}
