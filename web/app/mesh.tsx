"use client";

/**
 * The ambient field behind the console.
 *
 * Three soft radial gradients that drift very slowly against each other.
 * It is the difference between a page that sits on a flat colour and one
 * that sits in a space, and it costs almost nothing: no canvas, no
 * requestAnimationFrame, no library - three divs with a CSS keyframe on
 * `transform` and `opacity` only, which the compositor handles without
 * touching layout or paint.
 *
 * It is deliberately behind everything at low opacity. At the point where
 * you would describe it as "a background animation" it has gone too far -
 * the job is depth, not decoration, and every screen it sits behind has
 * text on it that someone is trying to read.
 *
 * Under prefers-reduced-motion the drift stops but the field stays: it is
 * depth, and depth is not motion. That is handled in mesh.module.css
 * rather than here, so it holds even if this component is rendered by
 * something that forgot to think about it.
 */

import s from "./mesh.module.css";

export function AmbientMesh({
  variant = "page",
}: {
  /** `page` is the calm default. `hero` is brighter and larger, for the
   * rounds screen and the report's verdict block, where there is space for
   * it and something worth framing. */
  variant?: "page" | "hero";
}) {
  return (
    <div
      className={`${s.mesh} ${variant === "hero" ? s.meshHero : ""}`}
      aria-hidden="true"
    >
      <span className={`${s.blob} ${s.blobA}`} />
      <span className={`${s.blob} ${s.blobB}`} />
      <span className={`${s.blob} ${s.blobC}`} />
      <span className={s.grain} />
    </div>
  );
}
