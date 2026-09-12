import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./tokens.css";
import "./globals.css";
import { Motion } from "./providers";

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

/* Applies a remembered theme before first paint.
 *
 * Without it the page renders in light, then the toggle hydrates and
 * switches it - a white flash straight in the face of anyone who chose
 * dark. It has to be inline and it has to be synchronous in <head>, which
 * is the one thing a React effect cannot be.
 *
 * Reading storage is wrapped because it throws outright in some contexts
 * rather than returning null, and a theme preference is not worth a blank
 * page. */
const NO_FLASH = `try{var t=localStorage.getItem('cerebrum-theme');if(t==='dark'||t==='light'){document.documentElement.dataset.theme=t}}catch(e){}`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
      </head>
      <body>
        <Motion>{children}</Motion>
      </body>
    </html>
  );
}
