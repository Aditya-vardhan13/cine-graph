"use client";

import { useCallback, useEffect, useState } from "react";
import "./rights.css";

type Decision = { decision: string; version: number; basis_url: string | null;
  notes: string; reviewer: string; created_at: string | null };
type ReviewItem = { snapshot_id: string; source_name: string; source_url: string;
  source_revision: string | null; retrieved_at: string | null; license: string;
  attribution_url: string | null; content_hash: string; films: string[];
  section_count: number; samples: { section: string; excerpt: string }[];
  latest_decision: Decision | null };

const endpoint = "/api/admin/rights";

export default function RightsReviewPage() {
  const [email, setEmail] = useState("");
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [basis, setBasis] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!email.trim()) { setItems([]); return; }
    try {
      const response = await fetch(`${endpoint}/queue?limit=100`, {
        headers: { "x-operator-email": email.trim() }, cache: "no-store",
      });
      const body = await response.json();
      if (!response.ok) { setMessage(body.detail ?? "Could not load review queue"); return; }
      setItems(body.items ?? []);
      setMessage("");
    } catch { setMessage("Could not reach the local API"); }
  }, [email]);

  useEffect(() => { void refresh(); }, [refresh]);

  async function decide(item: ReviewItem, decision: "approved" | "denied" | "review_required") {
    const rationale = notes[item.snapshot_id]?.trim() ?? "";
    if (rationale.length < 8) { setMessage("Add a short rationale for this decision first."); return; }
    setBusy(item.snapshot_id);
    setMessage("");
    try {
      const response = await fetch(`${endpoint}/${item.snapshot_id}`, {
        method: "POST",
        headers: { "x-operator-email": email.trim(), "content-type": "application/json" },
        body: JSON.stringify({ decision, decision_notes: rationale,
          decision_basis_url: basis[item.snapshot_id]?.trim() || null }),
      });
      const body = await response.json();
      if (!response.ok) { setMessage(body.detail ?? "Could not record decision"); return; }
      setMessage(`Recorded ${decision} as decision v${body.latest_decision.version}.`);
      await refresh();
    } catch { setMessage("Could not reach the local API"); }
    finally { setBusy(null); }
  }

  return <main className="rights-shell">
    <header className="rights-head">
      <a href="/admin/intake">← Film intake</a>
      <span className="rights-kicker">CineGraph · Local operator desk</span>
      <h1>Narrative-use review</h1>
      <p>Review each immutable source snapshot before its passages can be embedded or sent to a model. Decisions are versioned per snapshot, not inherited by every item from a source.</p>
    </header>
    <section className="rights-access">
      <label htmlFor="rights-email">Operator email</label>
      <input id="rights-email" type="email" value={email} onChange={event => setEmail(event.target.value)}
        autoComplete="email" placeholder="adityavk1310@gmail.com" />
      <p>Local pilot only. This operator log is not legal advice: an approval should be grounded in rights that cover the intended indexing and model-input use, not merely public visibility or attribution.</p>
    </section>
    {message && <p className="rights-message" role="status">{message}</p>}
    <div className="rights-summary">{items.length} source snapshot{items.length === 1 ? "" : "s"} · purpose: semantic indexing and model input</div>
    <section className="rights-list" aria-label="Source snapshots awaiting or with review">
      {!email.trim() ? <p className="rights-empty">Enter the configured local operator email to load the queue.</p> :
        items.length === 0 ? <p className="rights-empty">No narrative snapshots found in the current queue.</p> : items.map(item => {
          const current = item.latest_decision;
          return <article className="rights-card" key={item.snapshot_id}>
            <div className="rights-card-head">
              <div><span className={`rights-status status-${current?.decision ?? "review_required"}`}>{current?.decision ?? "review required"}{current ? ` · v${current.version}` : ""}</span>
                <h2>{item.films.join(" · ") || "Unmatched film"}</h2>
                <p>{item.source_name} · {item.license} · {item.section_count} sections · revision {item.source_revision ?? "not recorded"}</p>
              </div>
              <a href={item.source_url} target="_blank" rel="noreferrer">Open source ↗</a>
            </div>
            <div className="rights-links">
              <span>Attribution: {item.attribution_url ? <a href={item.attribution_url} target="_blank" rel="noreferrer">source attribution ↗</a> : "missing"}</span>
              <code>SHA-256 {item.content_hash}</code>
            </div>
            <div className="rights-samples">{item.samples.map((sample, index) => <details key={`${sample.section}-${index}`}>
              <summary>{sample.section}</summary><p>{sample.excerpt}</p>
            </details>)}</div>
            {current && <p className="rights-last-decision">Previous v{current.version}: {current.decision} by {current.reviewer}. {current.notes}</p>}
            <div className="rights-form">
              <label>Rights or policy basis URL
                <input type="url" value={basis[item.snapshot_id] ?? current?.basis_url ?? ""}
                  onChange={event => setBasis(values => ({ ...values, [item.snapshot_id]: event.target.value }))}
                  placeholder="https://…" />
              </label>
              <label>Decision rationale
                <textarea value={notes[item.snapshot_id] ?? ""}
                  onChange={event => setNotes(values => ({ ...values, [item.snapshot_id]: event.target.value }))}
                  placeholder="Record what was checked, scope, and any limits. This is retained in the decision history." />
              </label>
              <div className="rights-actions">
                <button type="button" disabled={busy === item.snapshot_id} onClick={() => void decide(item, "approved")}>Approve model use</button>
                <button type="button" disabled={busy === item.snapshot_id} onClick={() => void decide(item, "review_required")}>Defer</button>
                <button type="button" disabled={busy === item.snapshot_id} onClick={() => void decide(item, "denied")}>Deny</button>
              </div>
            </div>
          </article>;
        })}
    </section>
  </main>;
}
