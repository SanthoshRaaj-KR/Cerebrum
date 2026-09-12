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
 *    percentage to draw and no honest way to say which step is current.
 *    What these show instead is *what is being done* - the real steps, in
 *    the real order - under an indeterminate bar. A progress bar that
 *    creeps to 90% and waits is a lie about information the page does not
 *    have.
 *
 *    This is why there is no stepper here, though the desktop launcher has
 *    one: the launcher can watch two ports and knows for a fact when each
 *    service is up. This screen has no equivalent signal, and a stepper
 *    lighting up on a timer would be inventing one. The steps are
 *    presented as a set, all weighted equally, because that is the truth
 *    of what is known.
 *
 * 2. Say nothing evaluative. The wait after an answer is the interviewer
 *    reading it, and a spinner captioned "judging your answer" would leak
 *    the thing the whole judge/speak split exists to keep back. It says
 *    what is happening mechanically and stops there.
 *
 * All of it honours prefers-reduced-motion - the animations stop and the
 * states stay legible as plain text.
 */

import { motion } from "motion/react";
import { AmbientMesh } from "./mesh";
import { rise, stagger } from "./motion";
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
 * The mark, thinking.
 *
 * Two rings orbiting the wordmark's C at different rates. It carries no
 * information - it is the thing that makes a twenty-second wait feel
 * attended to rather than frozen - which is exactly why it is the first
 * thing to stop under reduced motion, where the glyph simply sits still.
 */
function ThinkingMark() {
  return (
    <div className={styles.mark} aria-hidden="true">
      <span className={styles.markRing} />
      <span className={styles.markRing2} />
      <span className={styles.markCore}>C</span>
    </div>
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
    <>
      <AmbientMesh variant="hero" />
      <motion.div
        className={styles.waiting}
        aria-live="polite"
        initial="hidden"
        animate="shown"
        variants={stagger(0.07)}
      >
        <motion.div variants={rise}>
          <ThinkingMark />
        </motion.div>
        <motion.p className={styles.waitTitle} variants={rise}>
          {title}
        </motion.p>
        <motion.div variants={rise} className={styles.waitBar}>
          <ProgressBar label="Setting up your interview" />
        </motion.div>
        <motion.ul className={styles.waitSteps} variants={stagger(0.08, 0.1)}>
          {steps.map((s) => (
            <motion.li key={s} variants={rise}>
              {s}
            </motion.li>
          ))}
        </motion.ul>
        <motion.p className={styles.waitNote} variants={rise}>
          {note}
        </motion.p>
      </motion.div>
    </>
  );
}

/**
 * The pause between submitting an answer and the next question landing.
 * Sits where the question will appear, so the eye is already in the right
 * place when it does.
 */
export function ThinkingTurn() {
  return (
    <motion.article
      className={styles.turn}
      aria-live="polite"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
    >
      <p className={styles.thinking}>
        <Dots label="Reading your answer, then picking what to ask next" />
      </p>
    </motion.article>
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
    <>
      <AmbientMesh variant="hero" />
      <motion.div
        className={styles.waiting}
        aria-live="polite"
        initial="hidden"
        animate="shown"
        variants={stagger(0.07)}
      >
        <motion.div variants={rise}>
          <ThinkingMark />
        </motion.div>
        <motion.p className={styles.waitTitle} variants={rise}>
          {title} · {count} question{count === 1 ? "" : "s"}
        </motion.p>
        <motion.div variants={rise} className={styles.waitBar}>
          <ProgressBar label="Writing your report" />
        </motion.div>
        <motion.ul className={styles.waitSteps} variants={stagger(0.08, 0.1)}>
          <motion.li variants={rise}>
            Finishing the per-answer judgements still running
          </motion.li>
          <motion.li variants={rise}>
            Weighing them against what the round set out to cover
          </motion.li>
          <motion.li variants={rise}>Writing the scorecard</motion.li>
        </motion.ul>
        <motion.p className={styles.waitNote} variants={rise}>
          This is the first point anything evaluative exists for you to see.
        </motion.p>
      </motion.div>
    </>
  );
}
