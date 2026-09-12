"use client";

/**
 * One place where the console decides how it moves.
 *
 * `reducedMotion="user"` makes every `motion` component honour the
 * system's prefers-reduced-motion setting: transforms and layout
 * animations are dropped, opacity changes are kept. That is the right
 * degradation - the information a fade carries (this is new, this
 * replaced that) survives, and the vestibular problem does not.
 *
 * Doing it here rather than per component is the whole point. Four dozen
 * call sites is four dozen chances to forget, and the one that forgets is
 * the one that makes somebody feel ill.
 *
 * The blanket CSS rule in globals.css stays as the backstop for anything
 * animated in CSS rather than by this library.
 */

import { MotionConfig } from "motion/react";

export function Motion({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
