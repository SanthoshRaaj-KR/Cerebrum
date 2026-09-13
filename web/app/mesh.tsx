"use client";

/**
 * The ground behind the console.
 *
 * There is no colour wash back here, and that is the design rather than a
 * limitation. Every coloured thing in this layer is a one-pixel line or a
 * two-pixel point; the field between them is obsidian and stays obsidian.
 * Soft blurred gradients are what every dark theme reaches for, and they
 * all end up looking like the same purple fog - so this reaches for the
 * opposite: a reading spreading across a sand table.
 *
 * Four static layers and one that breathes:
 *
 *   horizon   the only large area with a value on it, and it is a neutral.
 *   rings     concentric hairlines radiating from above the masthead.
 *   weave     the triangular lattice, full-bleed.
 *   nodes     nine points of charge, breathing out of phase with each
 *             other over 11-19 seconds.
 *   vignette  closes the frame so the light sits where the reading is.
 *
 * It costs almost nothing: no canvas, no requestAnimationFrame, no
 * library, no blur filter. Four gradients and nine 3px dots animating
 * `opacity`, which the compositor handles without touching layout or
 * paint. Under prefers-reduced-motion the charge settles and everything
 * else stays - structure is not motion, and removing it would leave a
 * flat page rather than a calm one.
 */

import s from "./mesh.module.css";

/* Nine, placed toward the edges. Few enough that the eye finds them rather
 * than being led around by them, and out of the middle because the middle
 * is where the reading is. */
const NODES = [s.n1, s.n2, s.n3, s.n4, s.n5, s.n6, s.n7, s.n8, s.n9];

export function AmbientMesh({
  variant = "page",
}: {
  /** `page` is the calm default. `hero` turns the reading up a little, for
   * the rounds screen, the report's verdict and the library header - where
   * there is space for it and something worth framing. */
  variant?: "page" | "hero";
}) {
  return (
    <div
      className={`${s.mesh} ${variant === "hero" ? s.meshHero : ""}`}
      aria-hidden="true"
    >
      {/* Order matters: the lattice is etched over the rings, the charge
          sits on the lattice, and the vignette closes over all of it. */}
      <span className={s.horizon} />
      <span className={s.rings} />
      <span className={s.weave} />
      {NODES.map((n, i) => (
        <span key={i} className={`${s.node} ${n}`} />
      ))}
      <span className={s.vignette} />
      <span className={s.grain} />
    </div>
  );
}
