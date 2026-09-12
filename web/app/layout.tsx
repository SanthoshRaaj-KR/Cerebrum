import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./tokens.css";
import "./globals.css";

/* IBM Plex, per design-system/cerebrum/MASTER.md: trustworthy and
 * professional, and built for data. One superfamily in two voices - Sans
 * for everything read as prose, Mono for the numerics, competency labels
 * and module names - so the console can show structure without importing a
 * second typeface with a personality of its own.
 *
 * next/font self-hosts both and emits font-display: swap, so no network
 * round-trip to Google and no invisible text while they load. */
const plexSans = IBM_Plex_Sans({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cerebrum",
  description:
    "A mock technical interview that researches the role, adapts to your answers, and reports back in detail.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
