"use client";

/**
 * Data visualisation for the report and the library.
 *
 * Hand-rolled SVG rather than a chart library. The data here is four
 * shapes and none of them needs axes, tooltips, zoom or a legend engine -
 * a charting dependency would cost more than it saved and would fight the
 * token system for control of colour.
 *
 * Every chart in this file is decoration over a fact that is also written
 * down somewhere: the score ring sits next to the number, the radar sits
 * above the competency table, the sparkline above a list of interviews.
 * None of them is the only way to get the information, which is what
 * makes them safe to draw in colour and shape alone.
 */

import { useEffect, useRef, useState } from "react";
import { animate, motion, useInView, useReducedMotion } from "motion/react";
import s from "./charts.module.css";

/** Counts a number up when it scrolls into view.
 *
 * A score that is simply printed is a fact. A score that counts up reads
 * as a result being computed - which is what actually happened, in the
 * background, while the interview was still running.
 *
 * Under reduced motion it renders the final value immediately: the number
 * is the information, the count is not. */
function useCountUp(value: number, decimals = 1) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduced = useReducedMotion();
  const [shown, setShown] = useState(reduced ? value : 0);

  useEffect(() => {
    if (!inView) return;
    if (reduced) {
      setShown(value);
      return;
    }
    const controls = animate(0, value, {
      duration: 1.1,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => setShown(v),
    });
    return () => controls.stop();
  }, [inView, value, reduced]);

  return { ref, text: shown.toFixed(decimals) };
}

export function CountUp({
  value,
  decimals = 1,
  className,
}: {
  value: number;
  decimals?: number;
  className?: string;
}) {
  const { ref, text } = useCountUp(value, decimals);
  return (
    <span ref={ref} className={className}>
      {text}
    </span>
  );
}

/**
 * The score, as a ring.
 *
 * Drawn with stroke-dasharray on a circle: one path, no arithmetic on
 * arcs, and the sweep animates by changing a single number. Rotated -90deg
 * so it starts at twelve o'clock, because a gauge that starts at three
 * reads as a pie chart.
 */
export function ScoreRing({
  score,
  size = 168,
  tone = "accent",
}: {
  score: number;
  size?: number;
  tone?: "accent" | "ok" | "warn" | "bad";
}) {
  const stroke = Math.max(6, Math.round(size * 0.055));
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, score / 10));

  const ref = useRef<SVGSVGElement | null>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduced = useReducedMotion();

  return (
    <svg
      ref={ref}
      className={`${s.ring} ${s[`ring_${tone}`]}`}
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`Score ${score} out of 10`}
    >
      <circle
        className={s.ringTrack}
        cx={size / 2}
        cy={size / 2}
        r={r}
        strokeWidth={stroke}
        fill="none"
      />
      <motion.circle
        className={s.ringFill}
        cx={size / 2}
        cy={size / 2}
        r={r}
        strokeWidth={stroke}
        fill="none"
        strokeLinecap="round"
        strokeDasharray={circumference}
        initial={{ strokeDashoffset: reduced ? circumference * (1 - pct) : circumference }}
        animate={
          inView ? { strokeDashoffset: circumference * (1 - pct) } : undefined
        }
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}

/**
 * Competencies as a shape.
 *
 * The point of a radar here is not precision - four statuses is not
 * precise data - it is that the *shape* of a lopsided interview is legible
 * at a glance in a way a list of four words is not. The table underneath
 * carries the actual reading, so this is allowed to be impressionistic.
 *
 * Below three axes a radar degenerates into a line or a point, so the
 * caller is expected not to render it; `Radar` returns null rather than
 * drawing something misleading.
 */
const RADAR_VALUE: Record<string, number> = {
  solid: 1,
  developing: 0.58,
  not_shown: 0.22,
  not_covered: 0.12,
};

export function Radar({
  points,
  size = 260,
}: {
  points: { name: string; status: string }[];
  size?: number;
}) {
  const ref = useRef<SVGSVGElement | null>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const reduced = useReducedMotion();

  if (points.length < 3) return null;

  const cx = size / 2;
  const cy = size / 2;
  const radius = size * 0.34;
  const step = (Math.PI * 2) / points.length;

  const at = (i: number, v: number) => {
    const angle = i * step - Math.PI / 2; // start at the top
    return [cx + Math.cos(angle) * radius * v, cy + Math.sin(angle) * radius * v];
  };

  const shape = points
    .map((p, i) => at(i, RADAR_VALUE[p.status] ?? 0.2).join(","))
    .join(" ");

  const rings = [0.25, 0.5, 0.75, 1];

  return (
    <svg
      ref={ref}
      className={s.radar}
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`Competency shape across ${points.length} areas. The table below lists each one.`}
    >
      {rings.map((v) => (
        <polygon
          key={v}
          className={s.radarGrid}
          points={points.map((_, i) => at(i, v).join(",")).join(" ")}
        />
      ))}
      {points.map((_, i) => {
        const [x, y] = at(i, 1);
        return (
          <line key={i} className={s.radarSpoke} x1={cx} y1={cy} x2={x} y2={y} />
        );
      })}
      <motion.polygon
        className={s.radarShape}
        points={shape}
        initial={{ opacity: 0, scale: reduced ? 1 : 0.6 }}
        animate={inView ? { opacity: 1, scale: 1 } : undefined}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        style={{ transformOrigin: `${cx}px ${cy}px` }}
      />
      {points.map((p, i) => {
        const [x, y] = at(i, RADAR_VALUE[p.status] ?? 0.2);
        return <circle key={p.name} className={s.radarDot} cx={x} cy={y} r={3} />;
      })}
    </svg>
  );
}

/**
 * Score over time.
 *
 * Deliberately without a y-axis: the question the library header answers
 * is "is the line going up", not "what was interview four". Hovering a
 * point gives the exact figure, and the list underneath gives all of them.
 */
export function Sparkline({
  values,
  width = 520,
  height = 120,
}: {
  values: { score: number; label?: string }[];
  width?: number;
  height?: number;
}) {
  const reduced = useReducedMotion();
  if (values.length === 0) return null;

  const pad = 14;
  const w = width - pad * 2;
  const h = height - pad * 2;
  // Fixed 0-10 domain. Auto-scaling a score chart makes a run of 6.8s look
  // like wild swings, which is a lie told by an axis.
  const x = (i: number) =>
    pad + (values.length === 1 ? w / 2 : (i / (values.length - 1)) * w);
  const y = (v: number) => pad + h - (Math.max(0, Math.min(10, v)) / 10) * h;

  const line = values.map((v, i) => `${x(i)},${y(v.score)}`).join(" ");
  const area = `${pad},${pad + h} ${line} ${x(values.length - 1)},${pad + h}`;

  return (
    <svg
      className={s.spark}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={`Score across ${values.length} saved interviews, oldest first.`}
    >
      {[0, 5, 10].map((v) => (
        <line
          key={v}
          className={s.sparkGrid}
          x1={pad}
          x2={width - pad}
          y1={y(v)}
          y2={y(v)}
        />
      ))}
      <polygon className={s.sparkArea} points={area} />
      <motion.polyline
        className={s.sparkLine}
        points={line}
        fill="none"
        initial={reduced ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
      />
      {values.map((v, i) => (
        <circle
          key={i}
          className={s.sparkDot}
          cx={x(i)}
          cy={y(v.score)}
          r={4}
        >
          <title>{v.label ? `${v.label}: ${v.score}` : String(v.score)}</title>
        </circle>
      ))}
    </svg>
  );
}

/** A labelled bar that fills when scrolled to. The number is always
 * written next to it; the bar is the comparison, not the value. */
export function Bar({
  value,
  max = 10,
  tone = "accent",
}: {
  value: number;
  max?: number;
  tone?: "accent" | "ok" | "warn" | "bad";
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  const pct = Math.max(0, Math.min(100, (value / max) * 100));

  return (
    <div ref={ref} className={s.bar} aria-hidden="true">
      <motion.span
        className={`${s.barFill} ${s[`bar_${tone}`]}`}
        initial={{ width: 0 }}
        animate={inView ? { width: `${pct}%` } : undefined}
        transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
      />
    </div>
  );
}
