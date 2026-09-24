import type { Metadata } from "next";
import "./styles.css";
import "./quality.css";
import "./story-comparison.css";
import "./research-navigation.css";

export const metadata: Metadata = {
  title: "CineGraph · Cinema Explorer",
  description: "Compare films through source-backed story, craft, and reception evidence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
