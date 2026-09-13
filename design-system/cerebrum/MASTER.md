# Design System Master File

> **LOGIC:** When building a specific page, first check `design-system/pages/[page-name].md`.
> If that file exists, its rules **override** this Master file.
> If not, strictly follow the rules below.

---

**Project:** Cerebrum
**Generated:** 2026-09-12 14:55:55
**Category:** General
**Design Dials:** Motion 3/10 (Subtle) | Density 5/10 (Standard)

---

## Global Rules

### Color Palette

| Role | Hex | CSS Variable |
|------|-----|--------------|
| Primary | `#0F172A` | `--color-primary` |
| On Primary | `#FFFFFF` | `--color-on-primary` |
| Secondary | `#334155` | `--color-secondary` |
| On Secondary | `#FFFFFF` | `--color-on-secondary` |
| Accent/CTA | `#0369A1` | `--color-accent` |
| On Accent/CTA | `#FFFFFF` | `--color-on-accent` |
| Background | `#F8FAFC` | `--color-background` |
| Foreground | `#020617` | `--color-foreground` |
| Card | `#FFFFFF` | `--color-card` |
| Card Foreground | `#020617` | `--color-card-foreground` |
| Muted | `#E8ECF1` | `--color-muted` |
| Muted Foreground | `#475569` | `--color-muted-foreground` |
| Border | `#E2E8F0` | `--color-border` |
| Destructive | `#DC2626` | `--color-destructive` |
| On Destructive | `#FFFFFF` | `--color-on-destructive` |
| Ring | `#0F172A` | `--color-ring` |

**Color Notes:** Professional navy + blue CTA

### Typography

- **Heading Font:** Lora
- **Body Font:** Raleway
- **Mood:** calm, wellness, health, relaxing, natural, organic
- **Google Fonts:** [Lora + Raleway](https://fonts.googleapis.com/css2?family=Lora:wght@400;500;600;700&family=Raleway:wght@300;400;500;600;700&display=swap)

**CSS Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Lora:wght@400;500;600;700&family=Raleway:wght@300;400;500;600;700&display=swap');
```

### Spacing Variables

*Density: 5/10 — Standard*

| Token | Value | Usage |
|-------|-------|-------|
| `--space-xs` | `4px` / `0.25rem` | Tight gaps |
| `--space-sm` | `8px` / `0.5rem` | Icon gaps, inline spacing |
| `--space-md` | `16px` / `1rem` | Standard padding |
| `--space-lg` | `24px` / `1.5rem` | Section padding |
| `--space-xl` | `32px` / `2rem` | Large gaps |
| `--space-2xl` | `48px` / `3rem` | Section margins |
| `--space-3xl` | `64px` / `4rem` | Hero padding |

### Shadow Depths

| Level | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift |
| `--shadow-md` | `0 4px 6px rgba(0,0,0,0.1)` | Cards, buttons |
| `--shadow-lg` | `0 10px 15px rgba(0,0,0,0.1)` | Modals, dropdowns |
| `--shadow-xl` | `0 20px 25px rgba(0,0,0,0.15)` | Hero images, featured cards |

---

## Component Specs

### Buttons

```css
/* Primary Button */
.btn-primary {
  background: #0369A1;
  color: white;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}

.btn-primary:hover {
  opacity: 0.9;
  transform: translateY(-1px);
}

/* Secondary Button */
.btn-secondary {
  background: transparent;
  color: #0F172A;
  border: 2px solid #0F172A;
  padding: 12px 24px;
  border-radius: 8px;
  font-weight: 600;
  transition: all 200ms ease;
  cursor: pointer;
}
```

### Cards

```css
.card {
  background: #F8FAFC;
  border-radius: 12px;
  padding: 24px;
  box-shadow: var(--shadow-md);
  transition: all 200ms ease;
  cursor: pointer;
}

.card:hover {
  box-shadow: var(--shadow-lg);
  transform: translateY(-2px);
}
```

### Inputs

```css
.input {
  padding: 12px 16px;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  font-size: 16px;
  transition: border-color 200ms ease;
}

.input:focus {
  border-color: #0F172A;
  outline: none;
  box-shadow: 0 0 0 3px #0F172A20;
}
```

### Modals

```css
.modal-overlay {
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
}

.modal {
  background: white;
  border-radius: 16px;
  padding: 32px;
  box-shadow: var(--shadow-xl);
  max-width: 500px;
  width: 90%;
}
```

---

## Style Guidelines

**Style:** Minimalism & Swiss Style

**Keywords:** Clean, simple, spacious, functional, white space, high contrast, geometric, sans-serif, grid-based, essential

**Best For:** Enterprise apps, dashboards, documentation sites, SaaS platforms, professional tools

**Key Effects:** Subtle hover (200-250ms), smooth transitions, sharp shadows if any, clear type hierarchy, fast loading

### Page Pattern

**Pattern Name:** Hero + Features + CTA

- **Conversion Strategy:** Deep CTA placement. For CTA label text, verify at least 4.5:1 against the button fill; use 7:1 only when the product explicitly targets AAA normal-text contrast. Keep focus and component boundaries independently visible. Disable hero parallax under reduced motion and render its static final state.
- **CTA Placement:** Hero (sticky) + Bottom
- **Section Order:** Hero with headline/image > Value prop > Key features (3-5) > CTA section > Footer

---

## Motion

**Hover Micro-interaction** (Subtle) — Trigger: hover | Duration: 150-200ms | Easing: `power1.out`

```js
gsap.to(el, { y: -1, opacity: 0.9, duration: 0.15, ease: 'power1.out' });
```

**Framework notes:** Bind on mouseenter/mouseleave; in React wrap in a ref + useEffect (or onMouseEnter/onMouseLeave props directly calling gsap.to); Use matchMedia('(prefers-reduced-motion: reduce)') to skip non-essential motion and render the final state immediately

- ✅ Keep displacement under 2px so it reads as feedback not motion
- ❌ Don't animate layout-affecting props (width/height/margin) on hover
- ⚡ Runs on transform/opacity only so it stays on the compositor thread

---

## Anti-Patterns (Do NOT Use)


### Additional Forbidden Patterns

- ❌ **Emojis as icons** — Use SVG icons (Heroicons, Lucide, Simple Icons)
- ❌ **Missing cursor:pointer** — All clickable elements must have cursor:pointer
- ❌ **Layout-shifting hovers** — Avoid scale transforms that shift layout
- ❌ **Low contrast text** — Maintain 4.5:1 minimum contrast ratio
- ❌ **Instant state changes** — Always use transitions (150-300ms)
- ❌ **Invisible focus states** — Focus states must be visible for a11y

---

## Pre-Delivery Checklist

Before delivering any UI code, verify:

- [ ] No emojis used as icons (use SVG instead)
- [ ] All icons from consistent icon set (Heroicons/Lucide)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover states with smooth transitions (150-300ms)
- [ ] Light mode: text contrast 4.5:1 minimum
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected
- [ ] Responsive: 375px, 768px, 1024px, 1440px
- [ ] No content hidden behind fixed navbars
- [ ] No horizontal scroll on mobile


---

## Project decisions on top of the generated system

Two deliberate departures from what the generator returned, recorded here
so they are not "corrected" back later.

### Typography: IBM Plex Sans + IBM Plex Mono, not Lora/Raleway

The generated pairing (Lora / Raleway, "calm, wellness, spa") matched on
the word *calm* in the brief and is wrong for the product. This tool hands
someone a judgement about their career readiness; it needs to read as
credible, not soothing.

`--domain typography "professional editorial serious technical"` returns
**Financial Trust — IBM Plex Sans**: "trustworthy, professional, corporate,
serious… excellent for data". That is the register. IBM Plex Mono comes
from the same superfamily and carries the numerics, the competency labels
and the module names, so the console can show structure without importing
a second typeface with a different personality.

### Colour: keep both themes, light by default

The generated palette is the light professional navy (#0F172A primary,
#0369A1 accent). We keep it, and we keep a dark theme alongside it, per
`dark-mode-pairing` — designed together rather than inverted.

Light is the default because the report is the part of this product people
actually read: per-question breakdowns, what a strong answer sounds like,
coach notes. That is long-form reading, and it belongs on a light surface.
The interview screen works in either.

Dark variants are lighter, desaturated tonal versions rather than inverted
values, and each theme's contrast is checked on its own (`color-dark-mode`,
`color-accessible-pairs`).

### Semantic status colours

The generator gives `destructive` only. The report needs a full status set,
all verified at 4.5:1 or better on their own surface:

| Meaning | Light | Dark |
|---|---|---|
| Solid / correct | `#15803D` | `#4ADE80` |
| Developing / partial | `#B45309` | `#FBBF24` |
| Not shown / incorrect | `#DC2626` | `#F87171` |
| Informational | `#0369A1` | `#38BDF8` |

Per `color-not-only`, none of these ever carries meaning alone - every
status in the report is a word first and a colour second.

---

## Revision: depth and motion

The first build was correct and flat. The product behind it is not flat —
it researches a role, escalates difficulty, and writes a per-answer
analysis — and a screen that reports all of that as text in boxes
undersells it. This revision adds depth and motion without touching the
identity: same accent, same superfamily, same three-layer tokens.

### Depth

Three new semantic tokens per theme, in `tokens.css`:

| Token | What it is for |
|---|---|
| `--glass` / `--glass-border` / `--glass-blur` | Panels that sit *on* the ambient field rather than covering it |
| `--glow-accent` / `--glow-ok` / `--glow-bad` | Emphasis on the one element per screen that deserves it |
| `--mesh-1..3` | The three stops of the ambient gradient field |
| `--rail` | The line a timeline or stepper is drawn on |

Two rules hold:

- **Glass is opt-in per panel.** `backdrop-filter` is one of the few
  properties that genuinely costs something to composite, and a page where
  everything is glass has no hierarchy left to express.
- **Glass never carries long-form text.** `GlassCard solid` exists for
  that. A paragraph read through a blurred gradient is a paragraph read
  slowly, and the report is made of paragraphs.

Dark gets *more* mesh and *more opaque* surfaces than light. Glass over a
near-black ground loses its edge entirely; light needs the opposite
restraint, because a coloured wash under long-form reading is the fastest
way to make a report tiring.

### Motion

The motion dial moved from Subtle to Complex. One vocabulary in
`web/app/motion.ts`; nothing picks its own timing.

| | |
|---|---|
| Arrive | 320ms, `cubic-bezier(0.16, 1, 0.3, 1)` — decelerating |
| Leave | 210ms, `cubic-bezier(0.7, 0, 0.84, 0)` — accelerating, ~65% of arrival |
| Values | Spring, never a duration |
| Stagger | 45ms per item |

Three rules, from `duration-timing`, `exit-faster-than-enter` and
`spring-physics`:

1. Arrivals decelerate, departures accelerate. Reversing this is the most
   common reason motion feels wrong without anyone being able to say why.
2. An exit is quicker than its entrance. A UI that takes as long to get
   out of the way as it took to arrive feels like it is arguing with you.
3. Anything tracking a real value — a score, a meter, a position — uses a
   spring, so the number reads as having settled rather than as an
   animation having finished.

**Reduced motion is handled once**, by `<MotionConfig reducedMotion="user">`
at the root, with CSS guards on the handful of animations written in CSS
and the blanket `globals.css` rule as backstop. Per-component guards would
be four dozen chances to forget, and the one that forgot would be the one
that made somebody feel ill.

### Charts

Hand-rolled SVG — score ring, competency radar, score sparkline, bars.
Four shapes, none needing axes, zoom or a legend engine; a charting
dependency would cost more than it saved and would fight the tokens for
control of colour.

Per `color-not-only`, **every chart sits beside the fact it draws**: the
ring beside the number, the radar above the competency table, the
sparkline above the list. None is the only route to its information, which
is what makes it safe to draw in colour and shape alone — and what lets
the radar be dropped entirely below 56rem without losing anything.

### The one thing motion is not allowed to do

The interview screen may not express a judgement. The coverage
constellation uses exactly one colour: a node is lit or it is not. A
second colour would inevitably come to mean *and it went well*, and the
whole judge/speak split exists so that opinion cannot reach the candidate
mid-interview. Leaking it through a chart rather than a sentence would be
worse, not better.

---

## Revision: obsidian, vibranium and gold

The identity changed. Not the structure — three token layers, one
superfamily, charts beside the facts they draw, the constellation still
one colour — but the palette and the ground beneath it are new.

Every colour in the console resolved through the semantic layer already,
with no hex value in any component stylesheet, so the whole product
changed identity by editing `tokens.css`. That is what the discipline was
for, and it is the single strongest argument for keeping it.

### Three colours, three jobs

| | Job | Obsidian | Day |
|---|---|---|---|
| **Obsidian** | The ground. Black with a violet undertone, so the accent sits in the same family as the surface it lights rather than on top of it | `#07060C` → `#EBE6F0` | — |
| **Bone / ink** | The day ground. Warm paper, not white — white under a violet accent goes cold and clinical | — | `#F7F4EF` / `#1A1420` |
| **Vibranium** | Every deliberate action, and the only thing allowed to glow | `#C084FC` | `#6D28D9` |
| **Gold** | Chrome. Eyebrows, rules, corner etching, the launcher's sigil | `#E8C67E` | `#8A6413` |

**Gold is never a status colour and never appears on anything
evaluative.** This is load-bearing rather than stylistic. Pale gold and
amber sit close enough to be confused, so `warn` moved off amber onto a
saturated orange (`#FB923C` / `#B45309`) and gold is kept off every
surface a verdict can reach. Nobody should have to work out whether a gold
thing is telling them something went badly — it never is.

The revised status set, each verified on its own surface:

| Meaning | Day | Obsidian |
|---|---|---|
| Solid / correct | `#15803D` | `#4ADE80` |
| Developing / partial | `#B45309` | `#FB923C` |
| Not shown / incorrect | `#BE123C` | `#FB7185` |
| Informational | `#6D28D9` | `#C084FC` |

### Obsidian is the default; day is a real design

Reversed from the first build. The identity is a dark one and the console
should arrive looking like itself, including for a viewer whose browser
reports no preference — so obsidian lives on bare `:root` and day is the
branch. `ThemeToggle` queries `prefers-color-scheme: light` for exactly
that reason; querying for dark would disagree with the stylesheet for
anyone reporting no preference.

Day is not an inversion. Bone and ink with a deep violet and an antique
gold, contrast verified on its own surfaces, because the report is still
long-form reading. Bright gold on bone is about 1.6:1, so day takes the
dark end of the gold ramp and keeps the same job.

### The ground has no gradient patches in it

The first version of this revision used blurred radial blobs, and it
looked like every other dark theme: purple fog with text floating on it.
The rule now is explicit — **every coloured thing in the background is a
one-pixel line or a two-pixel point.** The field between them is obsidian
and stays obsidian.

| Layer | What it is |
|---|---|
| `horizon` | The only large area carrying a value, and it is a neutral: the top sits a shade above the bottom |
| `rings` | Concentric hairlines radiating from above the masthead. The hard 1px stop matters — a soft ring is a glow, and a glow at that scale is the patch this avoids |
| `weave` | The triangular lattice: three families of hairlines at 0/60/120°, which is what a triangular grid *is*. Full-bleed, because architecture that stops at the edge of the reading column is decoration pretending to be structure |
| `nodes` | Nine points of charge breathing out of phase over 11–19s, placed toward the edges because the middle is where the reading is |
| `vignette` | Closes the frame so the light sits where the reading is |

No blur filter anywhere, which also makes it the cheapest this layer has
ever been: four gradients and nine 3px dots animating `opacity`.

The same problem recurs at panel scale, hence `--glow-rim`: a bloom that
reads as feedback under a button becomes a coloured patch under something
the size of the verdict block, so large surfaces get a lit edge instead.

### Etching

Radii drop to 2/4/6 — the identity is cut, and a 10px radius reads as
moulded next to a triangular lattice. Not to zero, because a true 0 makes
glass edges look like a rendering fault at a non-integer DPR.

Panels that are the point of their screen get two gold corner brackets,
top-left and bottom-right. Diagonally opposed, never four: four brackets
close a panel into a frame and the content starts to feel contained. Both
are empty `::before`/`::after`, so nothing is conveyed by them that is not
also in the text.

### The exception that proves the gold rule

Every section eyebrow is mono, uppercase, 0.16em and gold. The
interviewer label on the live interview screen matches all of it except
the colour. Gold is how this theme says *look here*, and that label sits
directly above the question someone is being asked — the one place in the
product where nothing may compete for attention.

---

## Revision: the voice, and reading comfort

### The interviewer speaks now

It did not before, and the old reasoning was sound for what the product
was: the interview is typed and graded, so a voice bought nothing.

What changed is what the voice is *for*. It reads out the question that is
already on screen — a rehearsal aid, not a conversation. Speech is
asymmetric on purpose:

| | What it is |
|---|---|
| **In** | An input method. You speak, Deepgram transcribes, the text lands in the answer box, and the normal typed flow takes over |
| **Out** | One sentence — the question you can already see. It never reads a judgement, a score or a hint, because none of those reach this screen at all |

`/api/speak` checks the text against the session's own questions before a
single byte reaches Deepgram. *"Say this out loud"* is precisely the shape
of request that could otherwise read back a private per-turn note or the
crib sheet — both kept out of the browser and the database for the same
reason — so the endpoint speaks words already on the candidate's screen or
it speaks nothing.

Two voices, and the fallback is not decoration. Aura sounds like a person
but it is a network round trip standing in front of a question somebody is
waiting to hear, and every one of its failure modes is ordinary. Anything
that goes wrong falls through to `speechSynthesis` rather than surfacing an
error mid-question.

**The typewriter yields to the voice.** Two things pacing the same sentence
at two different speeds is worse than either alone, so with speech on the
question simply appears and the voice carries the pace.

**The voice switch is the same weight as the theme toggle.** Muting the
interviewer is not a bigger decision than switching to day, and a louder
control would imply it was.

### Ambient layers are tuned for the twentieth minute, not the first

The lattice, rings and charge points were all set by looking at a
screenshot for a second. The interview screen is looked at while someone
composes an answer under pressure, and at those values the eye kept
re-finding the pattern behind the words.

All three roughly halved. The test for an ambient layer is not "does this
look good" — it is **noticed once, then not again**.

The type moved with it: muted text up a step on the ramp (8.9:1 → 12.9:1
on obsidian), subtle text 5.2:1 → 6.7:1, and the live question from snug
leading to normal. A question is read once, by someone already
half-composing a reply; tight leading on three lines of that is work
nobody needed.
