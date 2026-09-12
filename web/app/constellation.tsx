"use client";

/**
 * The coverage constellation.
 *
 * One node per competency the round set out to examine, lighting up as
 * each gets asked about. It is the only live representation of the
 * interview's shape, and it is deliberately the *shape* and nothing else.
 *
 * Read this before changing it: **it shows what has been asked about, never
 * how it went.** No quality, no score, no colour that encodes a verdict.
 * The whole architecture keeps the agent that judges separate from the
 * agent that speaks so that an opinion cannot leak into the next question;
 * lighting a node green because an answer was strong would leak it to the
 * candidate instead, which is worse. A node is lit or it is not.
 *
 * That also means the data is safe to hold here: `researchBrief.competencies`
 * is the list of area names, which the bridge already sends, and the
 * "asked" set is derived from the private notes' focus - which the browser
 * never sees - so it is approximated from question count instead. An
 * approximation is fine: this is orientation, not a readout.
 */

import { motion } from "motion/react";
import s from "./constellation.module.css";

export function Constellation({
  competencies,
  asked,
  closing,
}: {
  competencies: string[];
  /** How many questions have been asked. Nodes light in order as the
   * interview progresses - the backend does not say which competency a
   * given question served, and asking it to would mean shipping the
   * evaluator's private read to the browser. */
  asked: number;
  closing: boolean;
}) {
  if (competencies.length < 3) return null;

  const size = 132;
  const cx = size / 2;
  const cy = size / 2;
  const radius = size * 0.34;
  const step = (Math.PI * 2) / competencies.length;

  const at = (i: number) => {
    const angle = i * step - Math.PI / 2;
    return [cx + Math.cos(angle) * radius, cy + Math.sin(angle) * radius];
  };

  // Nodes light in order, capped at the number of competencies. Closing
  // lights the rest: by then every area has had its turn.
  const lit = closing ? competencies.length : Math.min(asked, competencies.length);

  return (
    <div className={s.wrap}>
      <svg
        className={s.svg}
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role="img"
        aria-label={`${lit} of ${competencies.length} areas covered so far`}
      >
        {competencies.map((_, i) => {
          const [x, y] = at(i);
          const [nx, ny] = at((i + 1) % competencies.length);
          return (
            <line
              key={`e${i}`}
              className={`${s.edge} ${i < lit - 1 ? s.edgeOn : ""}`}
              x1={x}
              y1={y}
              x2={nx}
              y2={ny}
            />
          );
        })}

        {competencies.map((name, i) => {
          const [x, y] = at(i);
          const on = i < lit;
          return (
            <motion.circle
              key={name}
              className={`${s.node} ${on ? s.nodeOn : ""}`}
              cx={x}
              cy={y}
              r={on ? 4.5 : 3}
              initial={false}
              animate={{ r: on ? 4.5 : 3 }}
              transition={{ type: "spring", stiffness: 300, damping: 20 }}
            >
              <title>{name}</title>
            </motion.circle>
          );
        })}

        <circle className={s.core} cx={cx} cy={cy} r={2} />
      </svg>
      <span className={s.caption}>
        {lit} of {competencies.length} areas
      </span>
    </div>
  );
}
