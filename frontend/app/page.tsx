import Link from "next/link";
import { api, CorpusQuality } from "../lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  let coverage: CorpusQuality | null = null;
  try { coverage = await api<CorpusQuality>("/corpus/quality", 10); }
  catch { /* The invitation to study still works when coverage is unavailable. */ }

  return <main className="shell landing">
    <section className="landing-hero">
      <div>
        <p className="eyebrow">A research desk for film writers</p>
        <h1>Don’t copy a film.<br /><em>Understand its choices.</em></h1>
        <p className="intro">Bring a story problem. Find films that approach it differently, inspect the source passages yourself, then decide what your own story could do.</p>
        <div className="landing-actions"><Link className="primary-link" href="/study">Start a study <span>↗</span></Link><Link className="quiet-link" href="/catalog">Explore films →</Link></div>
      </div>
      <aside className="landing-example" aria-label="Example writing question">
        <span>Try a question</span>
        <p>What happens when the person we trust most is not human?</p>
        <div><span>01 · Find films</span><span>02 · Inspect evidence</span><span>03 · Make your move</span></div>
      </aside>
    </section>
    <section className="landing-path" aria-label="How CineGraph works">
      <Link href="/study"><small>01 / Discover</small><h2>Start with a question</h2><p>Search by title or follow candidate films surfaced by a writing problem.</p><span>Open the study desk ↗</span></Link>
      <Link href="/catalog"><small>02 / Research</small><h2>Read the source</h2><p>Explore story, production, reception, interpretation, and legacy passages by film.</p><span>Browse the film library ↗</span></Link>
      <Link href="/studies"><small>03 / Create</small><h2>Keep your own reading</h2><p>Pin passages, write the difference you see, and record an original choice for your story.</p><span>Open your studies ↗</span></Link>
    </section>
    <section className="landing-footnote"><p><span className="signal" /> {coverage ? `${coverage.research.films_with_passages.toLocaleString("en-IN")} films with source passages` : "Source-linked film research"}</p><p>Passage matches are research leads, not verified interpretations. You decide what the evidence means.</p><Link href="/lineage">Explore proven film lineage →</Link></section>
  </main>;
}
