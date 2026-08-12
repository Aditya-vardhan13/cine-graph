import Link from "next/link";
import { notFound } from "next/navigation";
import { api, Film, year } from "../../../lib/api";
import "./person.css";

type Person = {
  id: string;
  name: string;
  wikidata_id: string | null;
  aliases: string[];
  films: Film[];
  provenance: Array<{ source_name: string; source_reference: string; license: string }>;
};

export default async function PersonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let person: Person;
  try { person = await api<Person>(`/people/${id}`); } catch { notFound(); }
  return <main className="shell person-page">
    <header className="topbar"><Link href="/" className="brand"><span>C</span> CineGraph</Link><p>Film intelligence <i>·</i> public metadata</p></header>
    <Link href="/" className="back">← Back to catalog</Link>
    <section className="person-hero"><p className="eyebrow">Person profile</p><h1>{person.name}</h1><p>{person.aliases.length > 1 ? `Also known as ${person.aliases.filter((alias) => alias !== person.name).join(", ")}` : "Identity resolved from public structured metadata."}</p></section>
    <section className="person-filmography"><div><p className="eyebrow">Filmography</p><h2>{person.films.length} linked films</h2></div><div className="person-films">{person.films.map((film) => <Link href={`/films/${film.id}`} key={film.id}><span>{year(film.release_date)}</span><b>{film.title}</b><small>{film.genres.slice(0, 2).join(" · ") || "Genre unavailable"}</small></Link>)}</div></section>
    <section className="person-source"><p>Source evidence</p>{person.provenance.map((item, index) => <a key={index} href={item.source_reference} target="_blank">{item.source_name} · {item.license} ↗</a>)}</section>
  </main>;
}
