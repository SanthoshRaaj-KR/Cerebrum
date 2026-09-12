"use client";

/* Shared primitives. Everything visual in the console is built from these,
 * so a change to how a button or a status badge reads happens once. */

import { useEffect, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion } from "motion/react";
import s from "./ui.module.css";
import { IconCheck, IconMoon, IconSun } from "./icons";
import { ease, inView, pop, rise, stagger } from "./motion";

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

/* -- motion wrappers ------------------------------------------------------
 *
 * Thin on purpose. Each one exists so a screen can say "this section
 * arrives" without repeating the variant and the viewport config, and so
 * the timing can be changed in motion.ts rather than in forty files.
 */

/** A block that rises into place when it is scrolled to. */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
}) {
  return (
    <motion.div
      className={className}
      variants={rise}
      {...inView}
      transition={{ ...ease, delay }}
    >
      {children}
    </motion.div>
  );
}

/** A container whose direct children arrive one after another. Pair with
 * <Reveal> children, or anything using the `rise` variant. */
export function Stagger({
  children,
  className,
  step,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  step?: number;
  as?: "div" | "ul" | "section";
}) {
  const Tag = motion[as];
  return (
    <Tag className={className} variants={stagger(step)} {...inView}>
      {children}
    </Tag>
  );
}

/** One item inside a <Stagger>. */
export function StaggerItem({
  children,
  className,
  as = "div",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "li" | "article";
}) {
  const Tag = motion[as];
  return (
    <Tag className={className} variants={rise}>
      {children}
    </Tag>
  );
}

/* -- surfaces ------------------------------------------------------------- */

/** A panel that sits on the ambient mesh rather than covering it.
 * `solid` opts out for anything holding long-form text - a paragraph read
 * through a blurred gradient is a paragraph read slowly. */
export function GlassCard({
  children,
  className,
  solid,
  glow,
}: {
  children: React.ReactNode;
  className?: string;
  solid?: boolean;
  glow?: boolean;
}) {
  return (
    <div
      className={[s.glass, solid ? s.glassSolid : "", glow ? s.glassGlow : "", className]
        .filter(Boolean)
        .join(" ")}
    >
      {children}
    </div>
  );
}

/* -- feedback ------------------------------------------------------------- */

/**
 * A transient confirmation.
 *
 * Auto-dismisses, per the toast guideline, but is also a live region:
 * something that only announces itself by appearing in the corner has not
 * announced itself to anyone using a screen reader. `status` rather than
 * `alert` because a successful save is not an interruption.
 */
export function Toast({
  message,
  tone = "ok",
  onDone,
}: {
  message: string | null;
  tone?: "ok" | "bad";
  onDone: () => void;
}) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onDone, tone === "bad" ? 6000 : 4000);
    return () => clearTimeout(t);
  }, [message, tone, onDone]);

  return (
    <div className={s.toastWrap} role="status" aria-live="polite">
      <AnimatePresence>
        {message && (
          <motion.div
            className={`${s.toast} ${tone === "bad" ? s.toastBad : s.toastOk}`}
            variants={pop}
            initial="hidden"
            animate="shown"
            exit="exit"
          >
            {tone === "ok" && <IconCheck size={15} />}
            {message}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * A destructive action that asks first.
 *
 * Two presses rather than a modal: a dialog for deleting one row is heavy,
 * and it takes focus somewhere else and then has to give it back. The
 * armed state times out on its own so a stray click cannot leave a live
 * delete button sitting on the page.
 */
export function ConfirmButton({
  label,
  confirmLabel,
  onConfirm,
  disabled,
}: {
  label: React.ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  disabled?: boolean;
}) {
  const [armed, setArmed] = useState(false);

  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(t);
  }, [armed]);

  return (
    <Button
      variant={armed ? "secondary" : "ghost"}
      className={armed ? s.confirmArmed : ""}
      disabled={disabled}
      onClick={() => {
        if (armed) {
          onConfirm();
          setArmed(false);
        } else {
          setArmed(true);
        }
      }}
    >
      {armed ? confirmLabel : label}
    </Button>
  );
}

export const ui = s;
