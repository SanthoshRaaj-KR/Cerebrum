/**
 * The console's motion vocabulary.
 *
 * One file so the whole product moves with a single rhythm. A screen that
 * invents its own timing is the visual equivalent of a component with a
 * hex value in it.
 *
 * Three rules are encoded here rather than left to each call site:
 *
 *   Arrivals decelerate, departures accelerate. That is how things
 *   actually move, and reversing it is the single most common reason
 *   motion feels wrong without anyone being able to say why.
 *
 *   Exits are quicker than entrances (~65%). A UI that takes as long to
 *   get out of the way as it took to arrive feels like it is arguing.
 *
 *   Anything tracking a real value - a score, a meter, a position - uses a
 *   spring, not a duration. Springs carry the sense that a number settled
 *   rather than that an animation finished.
 *
 * Reduced motion is NOT handled here. It is handled once, at the root, by
 * <MotionConfig reducedMotion="user">, which turns every transform in
 * these variants into an opacity change and leaves the layout alone. Per
 * component guards would be four dozen chances to forget.
 */

import type { Transition, Variants } from "motion/react";

/** Matches --ease-out / --ease-in / --ease-spring in tokens.css. */
export const EASE_OUT = [0.16, 1, 0.3, 1] as const;
export const EASE_IN = [0.7, 0, 0.84, 0] as const;

export const DUR = {
  fast: 0.12,
  base: 0.2,
  slow: 0.32,
  slower: 0.56,
  exit: 0.21,
} as const;

/** Per item in a list. Below ~30ms a stagger reads as one blur; above
 * ~60ms the last card feels like it is late rather than sequenced. */
export const STAGGER = 0.045;

export const ease: Transition = { duration: DUR.slow, ease: EASE_OUT };
export const easeFast: Transition = { duration: DUR.base, ease: EASE_OUT };

/** For values, not for entrances. */
export const spring: Transition = {
  type: "spring",
  stiffness: 220,
  damping: 30,
  mass: 0.9,
};

/** Softer, for anything large enough that overshoot would read as a wobble. */
export const springSoft: Transition = {
  type: "spring",
  stiffness: 120,
  damping: 24,
};

// -- entrance variants -------------------------------------------------------

/** The default: arrive from just below, leave upward and faster. */
export const rise: Variants = {
  hidden: { opacity: 0, y: 12 },
  shown: { opacity: 1, y: 0, transition: ease },
  exit: { opacity: 0, y: -8, transition: { duration: DUR.exit, ease: EASE_IN } },
};

export const riseFar: Variants = {
  hidden: { opacity: 0, y: 24 },
  shown: { opacity: 1, y: 0, transition: { duration: DUR.slower, ease: EASE_OUT } },
  exit: { opacity: 0, y: -12, transition: { duration: DUR.exit, ease: EASE_IN } },
};

export const fade: Variants = {
  hidden: { opacity: 0 },
  shown: { opacity: 1, transition: ease },
  exit: { opacity: 0, transition: { duration: DUR.exit, ease: EASE_IN } },
};

/** Grows from its own centre. For things that appear in place - a stamp, a
 * badge, a toast - rather than things that travel. */
export const pop: Variants = {
  hidden: { opacity: 0, scale: 0.92 },
  shown: { opacity: 1, scale: 1, transition: spring },
  exit: { opacity: 0, scale: 0.96, transition: { duration: DUR.exit, ease: EASE_IN } },
};

/**
 * A parent that sequences its children.
 *
 * `delayChildren` buys the container itself time to land first, so the
 * list does not start filling in before there is a list to fill.
 */
export const stagger = (step = STAGGER, delay = 0.04): Variants => ({
  hidden: {},
  shown: {
    transition: { staggerChildren: step, delayChildren: delay },
  },
  exit: {
    transition: { staggerChildren: step / 2, staggerDirection: -1 },
  },
});

/** Directional travel, for a question arriving or a screen replacing
 * another. Forward reads left-to-right; back reverses it, so the motion
 * agrees with which way you moved through the product. */
export const slide = (dir: 1 | -1 = 1): Variants => ({
  hidden: { opacity: 0, x: 28 * dir },
  shown: { opacity: 1, x: 0, transition: { duration: DUR.slow, ease: EASE_OUT } },
  exit: {
    opacity: 0,
    x: -28 * dir,
    transition: { duration: DUR.exit, ease: EASE_IN },
  },
});

/** Props for a scroll-triggered reveal. `once` because a section that
 * re-animates every time it scrolls back into view is a section you
 * cannot re-read. The margin fires it slightly before the edge, so it has
 * finished by the time it is properly in frame. */
export const inView = {
  initial: "hidden",
  whileInView: "shown",
  viewport: { once: true, margin: "-60px" },
} as const;
