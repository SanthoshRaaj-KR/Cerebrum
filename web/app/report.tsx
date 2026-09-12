"use client";

/**
 * The report.
 *
 * The only evaluative screen in the product, and the one people actually
 * read. It is deliberately long: a verdict tells you where you stand, and
 * only the question-by-question section tells you what to do about it.
 *
 * The order is chosen. Verdict first, because that is the question anyone
 * opens this to answer and burying it reads as evasion. Then the summary,
 * then the per-question breakdown, which is the substance. Competencies
 * and coach notes after, and the provenance last - it matters for trust
 * but nobody needs it before they know how they did.
 *
 * Every status is a word before it is a colour, and every chart here sits
 * next to the number or the table it draws - so the whole report survives
 * being read by someone who cannot tell the colours apart, or who has
 * turned the motion off.
 *
 * One component, two sources. A live report and one read back out of the
 * database render through here identically, from the same `ReportView`.
 * Two components would drift, and the saved one - the one you go back to
 * months later - would be the one that rotted.
 */

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { AnswerVerdict, CompetencyResult, Scorecard } from "@/lib/api";
import { CountUp, Radar, ScoreRing } from "./charts";
import {
  IconArrowLeft,
  IconBookmark,
  IconCheck,
  IconChevron,
  IconCross,
  IconMinus,
  ModeIcon,
} from "./icons";
import { AmbientMesh } from "./mesh";
import { inView, rise, stagger } from "./motion";
import { Badge, Button, GlassCard, Reveal, ThemeToggle, ui } from "./ui";
import s from "./report.module.css";

/** Everything the report renders, from wherever it came. */
export type ReportView = {
  mode: { key: string; name: string };
  role: string;
  questionCount: number;
  card: Scorecard;
  /** Absent on a live report - it is happening now. */
  savedAt?: string | null;
  provenance: {
    scorerModel: string | null;
    /** Unknown for a saved report, which predates the flag being stored. */
    doubleCheckWrong?: boolean;
  } | null;
};

const VERDICT_LABEL: Record<Scorecard["verdict"], string> = {
  strong_yes: "Strong yes",
  yes: "Yes",
  borderline: "Borderline",
  not_yet: "Not yet",
};

const VERDICT_CLASS: Record<Scorecard["verdict"], string> = {
  strong_yes: s.stampStrong_yes,
  yes: s.stampYes,
  borderline: s.stampBorderline,
  not_yet: s.stampNot_yet,
};

/** The ring takes the verdict's colour, not the score's - so the ring and
 * the stamp beside it never disagree. */
const VERDICT_TONE: Record<Scorecard["verdict"], "ok" | "warn" | "bad"> = {
  strong_yes: "ok",
  yes: "ok",
  borderline: "warn",
  not_yet: "bad",
};

const STATUS_LABEL: Record<string, string> = {
  solid: "Solid",
  developing: "Developing",
  not_shown: "Not shown",
  not_covered: "Not covered",
};

const STATUS_TONE: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  solid: "ok",
  developing: "warn",
  not_shown: "bad",
  not_covered: "neutral",
};

const DEPTH_LABEL: Record<AnswerVerdict["depth"], string> = {
  solid: "Solid",
  partial: "Partial",
  absent: "Missed",
};

const DEPTH_TONE: Record<AnswerVerdict["depth"], "ok" | "warn" | "bad"> = {
  solid: "ok",
  partial: "warn",
  absent: "bad",
};

function DepthIcon({ depth }: { depth: AnswerVerdict["depth"] }) {
  if (depth === "solid") return <IconCheck size={13} />;
  if (depth === "partial") return <IconMinus size={13} />;
  return <IconCross size={13} />;
}

/* -- section navigation -----------------------------------------------------
 *
 * A report this long needs a way back to the top of a section. The nav is
 * sticky and marks where you are, which is the cheap version of a table of
 * contents and much easier to keep honest: the sections are the source, and
 * an IntersectionObserver says which one you are in.
 */

const SECTIONS = [
  ["verdict", "Verdict"],
  ["answers", "Question by question"],
  ["areas", "By area"],
  ["notes", "Coach notes"],
  ["how", "How it was judged"],
] as const;

function useActiveSection(ids: string[]) {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    const seen = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          seen.set(e.target.id, e.intersectionRatio);
        }
        // Whichever tracked section is showing the most of itself wins.
        let best = "";
        let bestRatio = 0;
        for (const [id, ratio] of seen) {
          if (ratio > bestRatio) {
            best = id;
            bestRatio = ratio;
          }
        }
        if (best) setActive(best);
      },
      { threshold: [0, 0.15, 0.4, 0.75, 1], rootMargin: "-80px 0px -50% 0px" }
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [ids]);
  return active;
}

function SectionNav({ present }: { present: Set<string> }) {
  const ids = SECTIONS.filter(([id]) => present.has(id)).map(([id]) => id);
  const active = useActiveSection(ids);

  if (ids.length < 3) return null;

  return (
    <nav className={s.nav} aria-label="Report sections">
      <ul className={s.navList}>
        {SECTIONS.filter(([id]) => present.has(id)).map(([id, label]) => (
          <li key={id}>
            <a
              href={`#${id}`}
              className={`${s.navLink} ${active === id ? s.navLinkOn : ""}`}
              aria-current={active === id ? "true" : undefined}
            >
              {label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/* -- one question -----------------------------------------------------------
 *
 * Open by default. Everything under the fold here is the part that makes
 * the report worth reading, and hiding it behind a click to make the page
 * look tidier would be optimising the screenshot rather than the reader.
 * Collapsing is for skimming back over it later.
 */
function QuestionCard({
  v,
  open,
  onToggle,
}: {
  v: AnswerVerdict;
  open: boolean;
  onToggle: () => void;
}) {
  const rule =
    v.depth === "solid"
      ? s.itemSolid
      : v.depth === "partial"
        ? s.itemPartial
        : s.itemAbsent;

  const blocks: { label: string; text: string; className?: string }[] = [];
  if (v.evidence) blocks.push({ label: "What that showed", text: v.evidence });
  if (v.gap)
    blocks.push({
      label: v.correct ? "What was still missing" : "What went wrong",
      text: v.gap,
    });
  if (v.better)
    blocks.push({
      label: v.correct
        ? "What would have taken it further"
        : "What a strong answer sounds like",
      text: v.better,
      className: s.blockBetter,
    });
  if (v.improve)
    blocks.push({ label: "Next time", text: v.improve, className: s.blockImprove });

  return (
    <motion.article className={`${s.item} ${rule}`} variants={rise}>
      <span className={s.itemDot} aria-hidden="true">
        {v.index}
      </span>

      <header className={s.itemHead}>
        <div className={s.itemHeadText}>
          <p className={s.qNum}>
            Question {v.index}
            {v.competency && ` · ${v.competency}`}
          </p>
          <h3 className={s.qText}>{v.question}</h3>
        </div>
        <div className={s.itemHeadSide}>
          <Badge tone={DEPTH_TONE[v.depth]}>
            <DepthIcon depth={v.depth} />
            {DEPTH_LABEL[v.depth]}
          </Badge>
          {blocks.length > 0 && (
            <button
              type="button"
              className={s.disclose}
              onClick={onToggle}
              aria-expanded={open}
              aria-label={
                open
                  ? `Hide the analysis of question ${v.index}`
                  : `Show the analysis of question ${v.index}`
              }
            >
              <motion.span
                animate={{ rotate: open ? 180 : 0 }}
                transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                className={s.discloseIcon}
              >
                <IconChevron size={17} />
              </motion.span>
            </button>
          )}
        </div>
      </header>

      <div className={s.itemBody}>
        {/* Always visible: what you actually said. The analysis is the part
            that folds away, never the evidence it is about. */}
        <section className={s.block}>
          <p className={s.blockLabel}>What you said</p>
          <p className={`${s.blockText} ${s.yourAnswer}`}>
            {v.skipped ? <em>You skipped this one.</em> : v.answer || <em>—</em>}
          </p>
        </section>

        <AnimatePresence initial={false}>
          {open && (
            <motion.div
              key="analysis"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className={s.collapse}
            >
              {blocks.map((b) => (
                <section key={b.label} className={`${s.block} ${b.className ?? ""}`}>
                  <p className={s.blockLabel}>{b.label}</p>
                  <p className={s.blockText}>{b.text}</p>
                </section>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.article>
  );
}

/* -- the verdict block ------------------------------------------------------ */

function Verdict({
  view,
  savedNote,
}: {
  view: ReportView;
  savedNote: string | null;
}) {
  const { card } = view;
  return (
    <GlassCard className={s.verdictCard} glow>
      <div className={s.verdictGrid}>
        <div className={s.ringWrap}>
          <ScoreRing score={card.score} tone={VERDICT_TONE[card.verdict]} />
          <div className={s.ringLabel}>
            <span className={s.scoreNum}>
              <CountUp value={card.score} />
            </span>
            <span className={s.scoreOf}>out of 10</span>
          </div>
        </div>

        <div className={s.verdictText}>
          <motion.span
            className={`${s.stamp} ${VERDICT_CLASS[card.verdict]}`}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ type: "spring", stiffness: 260, damping: 22, delay: 0.35 }}
          >
            {VERDICT_LABEL[card.verdict]}
          </motion.span>
          <h1 className={s.headline}>{card.headline}</h1>
          <p className={s.meta}>
            {view.questionCount} question{view.questionCount === 1 ? "" : "s"} ·
            judged against an entry-level bar
            {savedNote ? ` · ${savedNote}` : ""}
          </p>
        </div>
      </div>
    </GlassCard>
  );
}

/* -- the screen ------------------------------------------------------------- */

export function ReportScreen({
  view,
  onRestart,
  onSave,
  saveState,
  storageEnabled,
  backLabel,
}: {
  view: ReportView;
  onRestart: () => void;
  /** Absent when there is nothing to save - a report read back out of the
   * database is already saved. */
  onSave?: () => void;
  saveState?: "idle" | "saving" | "saved";
  storageEnabled?: boolean;
  backLabel?: string;
}) {
  const { card } = view;
  const answered = card.answers ?? [];
  const resumeRound = view.mode.key === "resume_projects";

  // Open by default; the toggle is for skimming back over it.
  const [collapsed, setCollapsed] = useState<Set<number>>(new Set());
  const allOpen = collapsed.size === 0;
  const headingRef = useRef<HTMLDivElement | null>(null);

  const present = new Set<string>(["verdict"]);
  if (answered.length > 0) present.add("answers");
  if (card.competencies.length > 0) present.add("areas");
  if (card.notes.length > 0) present.add("notes");
  if (view.provenance) present.add("how");

  const savedNote = view.savedAt
    ? new Date(view.savedAt).toLocaleDateString(undefined, {
        day: "numeric",
        month: "short",
        year: "numeric",
      })
    : null;

  function toggle(i: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  return (
    <>
      <AmbientMesh variant="hero" />
      <main className={`${ui.page} ${ui.pageWide}`} ref={headingRef}>
        <header className={s.top}>
          <div className={ui.eyebrow}>
            <ModeIcon mode={view.mode.key} size={14} />
            {view.mode.name}
            {view.role && ` · ${view.role}`}
          </div>
          <span className={ui.spacerFlex} />
          {/* Also at the top, not only in the footer. This page is long by
              design, and an action that lives solely past the last source
              link is an action most people never find. */}
          {onSave && storageEnabled && (
            <Button
              variant={saveState === "saved" ? "ghost" : "secondary"}
              onClick={onSave}
              disabled={saveState !== "idle"}
            >
              {saveState === "saved" ? (
                <IconCheck size={16} />
              ) : (
                <IconBookmark size={16} />
              )}
              {saveState === "saving"
                ? "Saving…"
                : saveState === "saved"
                  ? "Saved"
                  : "Store"}
            </Button>
          )}
          <Button variant="ghost" onClick={onRestart}>
            <IconArrowLeft size={16} />
            {backLabel ?? "Take another round"}
          </Button>
          <ThemeToggle />
        </header>

        <section id="verdict">
          <Verdict view={view} savedNote={savedNote} />
        </section>

        <SectionNav present={present} />

        {!card.grounded && (
          <p className={ui.notice}>
            {resumeRound
              ? "A competency map couldn't be built from the résumé this time, so this is based on the transcript alone."
              : "The role research didn't come back this time, so the competencies below come from the model's own knowledge rather than a live search."}
          </p>
        )}

        {(card.strengths.length > 0 || card.gaps.length > 0) && (
          <motion.div className={s.split} variants={stagger()} {...inView}>
            {card.strengths.length > 0 && (
              <motion.section variants={rise} className={s.splitCol}>
                <p className={ui.eyebrow}>What held up</p>
                <ul className={s.list}>
                  {card.strengths.map((x, i) => (
                    <li key={i} className={s.listItem}>
                      <span className={`${s.bullet} ${s.bulletOk}`} />
                      {x}
                    </li>
                  ))}
                </ul>
              </motion.section>
            )}

            {card.gaps.length > 0 && (
              <motion.section variants={rise} className={s.splitCol}>
                <p className={ui.eyebrow}>What didn&apos;t</p>
                <ul className={s.list}>
                  {card.gaps.map((x, i) => (
                    <li key={i} className={s.listItem}>
                      <span className={`${s.bullet} ${s.bulletBad}`} />
                      {x}
                    </li>
                  ))}
                </ul>
              </motion.section>
            )}
          </motion.div>
        )}

        {answered.length > 0 && (
          <section id="answers">
            <Reveal>
              <div className={s.sectionHead}>
                <div>
                  <p className={ui.eyebrow}>Question by question</p>
                  <h2 className={ui.sectionTitle}>Every answer, taken apart</h2>
                  <p className={ui.lede}>
                    Each one was judged on its own while the interview was still
                    running. This is where the verdict above came from.
                  </p>
                </div>
                <Button
                  variant="ghost"
                  onClick={() =>
                    setCollapsed(
                      allOpen ? new Set(answered.map((a) => a.index)) : new Set()
                    )
                  }
                >
                  {allOpen ? "Collapse all" : "Expand all"}
                </Button>
              </div>
            </Reveal>

            <motion.div className={s.qa} variants={stagger(0.05)} {...inView}>
              {answered.map((v) => (
                <QuestionCard
                  key={v.index}
                  v={v}
                  open={!collapsed.has(v.index)}
                  onToggle={() => toggle(v.index)}
                />
              ))}
            </motion.div>
          </section>
        )}

        {card.competencies.length > 0 && (
          <section id="areas">
            <Reveal>
              <p className={ui.eyebrow}>By area</p>
              <h2 className={ui.sectionTitle}>
                {resumeRound
                  ? "What your own work showed"
                  : "What this role expects of a fresher"}
              </h2>
            </Reveal>

            <div className={s.areas}>
              {/* The radar is the shape of the interview at a glance; the
                  table beside it is the actual reading. Neither is a
                  substitute for the other, which is why both are here. */}
              <Reveal className={s.radarWrap}>
                <Radar
                  points={card.competencies.map((c: CompetencyResult) => ({
                    name: c.name,
                    status: c.status,
                  }))}
                />
              </Reveal>

              <motion.div className={s.table} variants={stagger(0.04)} {...inView}>
                {card.competencies.map((c) => (
                  <motion.div key={c.name} className={s.row} variants={rise}>
                    <Badge tone={STATUS_TONE[c.status] ?? "neutral"}>
                      {STATUS_LABEL[c.status] ?? c.status}
                    </Badge>
                    <div>
                      <p className={s.rowName}>{c.name}</p>
                      {c.evidence && (
                        <p className={s.rowEvidence}>{c.evidence}</p>
                      )}
                    </div>
                  </motion.div>
                ))}
              </motion.div>
            </div>
          </section>
        )}

        {card.notes.length > 0 && (
          <section id="notes">
            <Reveal>
              <p className={ui.eyebrow}>Coach notes</p>
              <h2 className={ui.sectionTitle}>Patterns worth working on</h2>
            </Reveal>
            <motion.ul
              className={`${s.list} ${s.notesList}`}
              variants={stagger(0.05)}
              {...inView}
            >
              {card.notes.map((n, i) => (
                <motion.li key={i} className={s.listItem} variants={rise}>
                  <span className={s.bullet} />
                  {n}
                </motion.li>
              ))}
            </motion.ul>
          </section>
        )}

        {view.provenance && (
          <section id="how">
            <Reveal>
              <p className={ui.eyebrow}>How this was judged</p>
              <ul className={s.prov}>
                <li>
                  <strong>
                    Every answer was judged on its own, as you went.
                  </strong>{" "}
                  Each went to <code>{view.provenance.scorerModel}</code> in the
                  background while you were already reading the next question,
                  so it got real attention rather than a skim at the end.
                </li>
                <li>
                  <strong>None of it was visible during the interview.</strong>{" "}
                  The agent that judged and the agent that spoke to you were
                  separate calls — an opinion could not leak into the wording of
                  the next question.
                </li>
                {view.provenance.doubleCheckWrong && (
                  <li>
                    <strong>Wrong answers were double-checked.</strong> Anything
                    the fast read called incorrect got a second opinion on{" "}
                    <code>{view.provenance.scorerModel}</code> before it counted
                    — a vague-but-right answer is not a wrong one.
                  </li>
                )}
                <li>
                  <strong>Graded against a fresher bar.</strong> Naming the
                  concept, one worked example, and reasoning about a trade-off
                  out loud is a solid answer at this level. An honest &quot;I
                  don&apos;t know&quot; costs far less than a confident wrong
                  claim.
                </li>
                <li>
                  <strong>Nothing was scored on speed.</strong> There was no
                  clock; how long you took is not an input to any of this.
                </li>
              </ul>
            </Reveal>
          </section>
        )}

        {card.sources.length > 0 && (
          <Reveal>
            <section>
              <p className={ui.eyebrow}>Researched from</p>
              <ul className={s.sources}>
                {card.sources.map((u) => (
                  <li key={u}>
                    <a href={u} target="_blank" rel="noreferrer">
                      {u}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          </Reveal>
        )}

        <div className={s.footer}>
          <Button variant="primary" onClick={onRestart}>
            <IconArrowLeft size={16} />
            {backLabel ?? "Take another round"}
          </Button>

          {onSave && (
            <Button
              variant="secondary"
              onClick={onSave}
              disabled={!storageEnabled || saveState !== "idle"}
            >
              {saveState === "saved" ? (
                <IconCheck size={16} />
              ) : (
                <IconBookmark size={16} />
              )}
              {saveState === "saving"
                ? "Saving…"
                : saveState === "saved"
                  ? "Saved to your library"
                  : "Store this interview"}
            </Button>
          )}

          {onSave && !storageEnabled && (
            <span className={s.footNote}>
              Add <code>MONGODB_URI</code> to <code>.env</code> to keep your
              interviews.
            </span>
          )}
        </div>
      </main>
    </>
  );
}
