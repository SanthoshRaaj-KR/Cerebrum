"use client";

/**
 * The waiting states.
 *
 * This console asks a model to do real work at three points, and each wait
 * is long enough that a disabled button is not an answer: starting a
 * session runs a résumé digest plus either a web search or a gateway call
 * and then writes the opening question; every answer is read, judged and
 * reacted to; the report waits on every background judgement still in
 * flight. Fifteen to thirty seconds of a greyed-out button reads as a hung
 * page.
 *
 * Two rules these components follow:
 *
 * 1. Never fake progress. The backend does its work behind one blocking
 *    request and reports nothing until it returns, so there is no honest
 *    percentage to draw. What these show instead is *what is being done* -
 *    the real steps, in the real order - under an indeterminate bar. A
 *    progress bar that creeps to 90% and waits is a lie about information
 *    the page does not have.
 * 2. Say nothing evaluative. The wait after an answer is the interviewer
 *    reading it, and a spinner captioned "judging your answer" would leak
 *    the thing the whole judge/speak split exists to keep back. It says
 *    what is happening mechanically and stops there.
 *
 * All of it honours prefers-reduced-motion (see page.module.css) - the
 * animations stop and the states stay legible as plain text.
 */

import styles from "./waiting.module.css";

/** An indeterminate bar. Honest about knowing only "still working". */
export function ProgressBar({ label }: { label?: string }) {
  return (
    <div
      className={styles.progressWrap}
      role="progressbar"
      aria-label={label || "Working"}
    >
      <span className={styles.progressBar} />
    </div>
  );
}

/** Three dots, for a short inline wait where a bar would be too much. */
export function Dots({ label }: { label: string }) {
  return (
    <span className={styles.dotsRow}>
      <span className={styles.dots} aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      {label}
    </span>
  );
}

/**
 * The session-start wait. Lists the work actually being done, in order,
 * with no claim about which step is current - because the backend does not
 * say. `note` carries the honest expectation of how long it takes.
 */
export function StartingUp({
  title,
  steps,
  note,
}: {
  title: string;
  steps: string[];
  note: string;
}) {
  return (
    <div className={styles.waiting} aria-live="polite">
      <p className={styles.waitTitle}>{title}</p>
      <ProgressBar label="Setting up your interview" />
      <ul className={styles.waitSteps}>
        {steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
      <p className={styles.waitNote}>{note}</p>
    </div>
  );
}

/**
 * The pause between submitting an answer and the next question landing.
 * Sits where the question will appear, so the eye is already in the right
 * place when it does.
 */
export function ThinkingTurn() {
  return (
    <article className={styles.turn} aria-live="polite">
      <p className={styles.thinking}>
        <Dots label="Reading your answer, then picking what to ask next" />
      </p>
    </article>
  );
}

/** The end-of-interview wait, while the scorecard is written. */
export function BuildingReport({
  title,
  count,
}: {
  title: string;
  count: number;
}) {
  return (
    <div className={styles.waiting} aria-live="polite">
      <p className={styles.waitTitle}>
        {title} · {count} question{count === 1 ? "" : "s"}
      </p>
      <ProgressBar label="Writing your report" />
      <ul className={styles.waitSteps}>
        <li>Finishing the per-answer judgements still running</li>
        <li>Weighing them against what the round set out to cover</li>
        <li>Writing the scorecard</li>
      </ul>
      <p className={styles.waitNote}>
        This is the first point anything evaluative exists for you to see.
      </p>
    </div>
  );
}
