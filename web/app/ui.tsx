"use client";

/* Shared primitives. Everything visual in the console is built from these,
 * so a change to how a button or a status badge reads happens once. */

import { useSyncExternalStore } from "react";
import s from "./ui.module.css";
import { IconMoon, IconSun } from "./icons";

type Tone = "ok" | "warn" | "bad" | "neutral";

const BADGE_TONE: Record<Tone, string> = {
  ok: s.badgeOk,
  warn: s.badgeWarn,
  bad: s.badgeBad,
  neutral: s.badgeNeutral,
};

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: React.ReactNode;
}) {
  return <span className={`${s.badge} ${BADGE_TONE[tone]}`}>{children}</span>;
}

export function Button({
  variant = "secondary",
  full,
  className,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
  full?: boolean;
}) {
  const variantClass =
    variant === "primary"
      ? s.btnPrimary
      : variant === "ghost"
        ? s.btnGhost
        : s.btnSecondary;
  return (
    <button
      {...rest}
      className={[s.btn, variantClass, full ? s.btnFull : "", className]
        .filter(Boolean)
        .join(" ")}
    />
  );
}

/**
 * How far through the interview we are.
 *
 * `planned` is the backend's estimate, not a schedule - the interview
 * really ends when every competency has a read. So the bar fills against
 * the estimate, caps at full rather than overflowing, and changes colour
 * once it is past it, which is the honest way to say "longer than
 * expected" without implying a deadline was missed. Nothing here is a
 * clock and nothing is ever scored on it.
 */
export function Meter({
  asked,
  planned,
  note,
  closing,
}: {
  asked: number;
  planned: number;
  note?: string;
  closing?: boolean;
}) {
  const over = asked > planned;
  const pct = planned > 0 ? Math.min(100, (asked / planned) * 100) : 0;
  const label = closing
    ? "Wrapping up"
    : `Question ${asked}${over ? "" : ` of about ${planned}`}`;

  return (
    <div className={s.meter}>
      <div className={s.meterHead}>
        <span className={s.meterCount}>{label}</span>
        {note && <span className={s.meterNote}>{note}</span>}
      </div>
      <div
        className={s.meterTrack}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={planned}
        aria-valuenow={Math.min(asked, planned)}
        aria-label="Interview progress"
      >
        <div
          className={`${s.meterFill} ${over ? s.meterFillOver : ""}`}
          style={{ width: `${closing ? 100 : pct}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Light/dark toggle.
 *
 * The theme lives on <html data-theme>, not in React - tokens.css reads it
 * there and an inline script in the layout applies it before first paint,
 * so a dark-preferring viewer never gets a white flash.
 *
 * That makes the DOM the source of truth and React the subscriber, which
 * is what useSyncExternalStore is for. Reading it into state inside an
 * effect instead would render once with the wrong icon and then correct
 * itself - a cascading render, and a visible flicker on the glyph.
 */
const THEME_EVENT = "cerebrum-theme";

function subscribe(onChange: () => void) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", onChange);
  window.addEventListener(THEME_EVENT, onChange);
  return () => {
    media.removeEventListener("change", onChange);
    window.removeEventListener(THEME_EVENT, onChange);
  };
}

function currentTheme(): "light" | "dark" {
  const set = document.documentElement.dataset.theme;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function ThemeToggle() {
  // The server has no way to know the viewer's preference, so it renders
  // the light-mode glyph; the inline script has already set the real theme
  // by the time this hydrates.
  const theme = useSyncExternalStore(subscribe, currentTheme, () => "light" as const);

  function flip() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("cerebrum-theme", next);
    } catch {
      // Not being able to remember the choice is no reason to refuse it.
    }
    window.dispatchEvent(new Event(THEME_EVENT));
  }

  return (
    <button
      type="button"
      className={s.themeToggle}
      onClick={flip}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    >
      {theme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
    </button>
  );
}

export const ui = s;
