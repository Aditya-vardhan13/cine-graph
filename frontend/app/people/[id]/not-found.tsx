import Link from "next/link";

export default function NotFound() { return <main className="shell empty"><p className="eyebrow">Not found</p><h1>This person is not in the current catalog.</h1><Link href="/">Return to Explorer</Link></main>; }
