"use client";

/* Shared primitives. Everything visual in the console is built from these,
 * so a change to how a button or a status badge reads happens once. */

import { useEffect, useState } from "react";
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
 * Writes data-theme on <html>, which tokens.css treats as beating the
 * system preference in both directions. The choice is remembered per
 * browser; every read and write is guarded because storage throws outright
 * in some contexts rather than merely coming back empty.
 */
export function ThemeToggle() {
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);

  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem("cerebrum-theme");
    } catch {
      /* storage unavailable - fall through to the system preference */
    }
    if (saved === "light" || saved === "dark") {
      setTheme(saved);
      document.documentElement.dataset.theme = saved;
    }
  }, []);

  function flip() {
    const current =
      theme ??
      (window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light");
    const next = current === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("cerebrum-theme", next);
    } catch {
      /* not being able to remember it is not a reason to refuse the flip */
    }
  }

  // Until the effect has run we don't know the effective theme, so the
  // label would be a guess. Show both glyphs and a neutral name instead of
  // rendering nothing, which would shift the header on hydration.
  const known = theme !== null;

  return (
    <button
      type="button"
      className={s.themeToggle}
      onClick={flip}
      aria-label={
        known
          ? `Switch to ${theme === "dark" ? "light" : "dark"} theme`
          : "Switch theme"
      }
      title="Switch theme"
    >
      {theme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
    </button>
  );
}

export const ui = s;
