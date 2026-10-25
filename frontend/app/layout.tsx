import type { Metadata } from "next";
import Link from "next/link";
import "./styles.css";
import "./quality.css";
import "./story-comparison.css";
import "./research-navigation.css";
import "./research-catalog-search.css";
import "./journey.css";

export const metadata: Metadata = {
  title: "CineGraph · A research desk for writers",
  description: "Study films through source-linked evidence and turn comparisons into your own creative decisions.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>
    <header className="site-header"><div className="shell topbar">
      <Link href="/" className="brand"><span>C</span> CineGraph</Link>
      <nav className="research-nav" aria-label="Main navigation">
        <Link href="/study">Study</Link><Link href="/catalog">Films</Link><Link href="/lineage">Lineage</Link><Link href="/studies">My studies</Link>
      </nav>
    </div></header>
    {children}
  </body></html>;
}
