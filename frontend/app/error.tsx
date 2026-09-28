"use client";

import Link from "next/link";

export default function ServiceError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="shell empty" role="alert">
    <p className="eyebrow">Connection interrupted</p>
    <h1>We couldn&apos;t load this view.</h1>
    <p>The research service may be temporarily unavailable. Your studies saved in this browser are not changed.</p>
    <button className="compare-button" onClick={reset}>Try again</button>
    <Link href="/">Return to the writer desk</Link>
  </main>;
}
