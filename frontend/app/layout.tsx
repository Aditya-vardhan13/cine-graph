import type { Metadata } from "next";
import "./styles.css";
import "./quality.css";

export const metadata: Metadata = {
  title: "CineGraph · Cinema Explorer",
  description: "Explore public, provenance-backed film metadata.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
