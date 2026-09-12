"use client";

/**
 * Picking a round, which for five rounds out of six is the whole of setup.
 *
 * The round IS the role - "SDE & Backend" already says Backend Engineer -
 * so there is nothing to type and each card starts the interview on one
 * click. That is why they are buttons rather than selection chips: there
 * is no second step to confirm them in.
 *
 * The résumé round is the exception, and only because a résumé is that
 * round's entire syllabus. It gets a second screen of its own, reached
 * only by choosing it - so nobody uploads a CV for a round that would
 * never have opened it.
 *
 * This is the first screen anyone sees, so it carries the most motion: the
 * cards arrive in sequence, and each one lifts and lights its own edge
 * under the pointer. All of it is entrance and hover - nothing here is
 * still moving once you have stopped looking at it.
 */

import { useState } from "react";
import { motion } from "motion/react";
import { Mode, SavedSummary, SystemInfo } from "@/lib/api";
import {
  IconArrowLeft,
  IconArrowRight,
  IconCheck,
  IconLibrary,
  IconSpark,
  ModeIcon,
} from "./icons";
import { AmbientMesh } from "./mesh";
import { ease, rise, stagger } from "./motion";
import { Button, GlassCard, ThemeToggle, ui } from "./ui";
import s from "./rounds.module.css";

const RESUME_MODE = "resume_projects";

function Masthead({
  subtitle,
  onLibrary,
}: {
  subtitle: string;
  /** Only passed when saving is switched on. Without a database the
   * library has nothing to show and nothing to offer, and a link into a
   * wall is worse than no link. */
  onLibrary?: () => void;
}) {
  return (
    <motion.header
      className={s.masthead}
      initial="hidden"
      animate="shown"
      variants={stagger(0.06)}
    >
      <div>
        <motion.h1 className={s.wordmark} variants={rise}>
          Cerebrum
        </motion.h1>
        <motion.p className={s.tagline} variants={rise}>
          {subtitle}
        </motion.p>
      </div>
      <motion.div className={s.mastheadActions} variants={rise}>
        {onLibrary && (
          <Button variant="secondary" onClick={onLibrary}>
            <IconLibrary size={16} />
            Library
          </Button>
        )}
        <ThemeToggle />
      </motion.div>
    </motion.header>
  );
}

/** The three claims worth making before someone has used it once. Facts
 * about how it behaves, not adjectives about how good it is. */
function Pitch() {
  const points = [
    ["Researched", "It looks up what that role is being asked right now, then builds the round from it."],
    ["Adaptive", "Answer well and the next question on that ground goes harder. Answer badly and it finds another way in."],
    ["Nothing held back", "No score while you're in it. At the end, every answer taken apart."],
  ];
  return (
    <motion.ul
      className={s.pitch}
      initial="hidden"
      animate="shown"
      variants={stagger(0.05, 0.12)}
    >
      {points.map(([title, body]) => (
        <motion.li key={title} className={s.pitchItem} variants={rise}>
          <span className={s.pitchIcon}>
            <IconCheck size={13} />
          </span>
          <span>
            <strong className={s.pitchTitle}>{title}</strong>
            <span className={s.pitchBody}>{body}</span>
          </span>
        </motion.li>
      ))}
    </motion.ul>
  );
}

/**
 * The strip of recent scores above the grid.
 *
 * Only ever shown when there is something saved - an empty "your history"
 * block on a first run is an advertisement for a feature, not a feature.
 */
function RecentStrip({
  recent,
  onOpen,
}: {
  recent: SavedSummary[];
  onOpen: () => void;
}) {
  if (recent.length === 0) return null;
  return (
    <motion.div
      className={s.recent}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...ease, delay: 0.2 }}
    >
      <span className={s.recentLabel}>Your last few</span>
      <span className={s.recentRow}>
        {recent.slice(0, 5).map((r) => (
          <span key={r.id} className={s.recentChip} title={`${r.mode.name} — ${r.score}/10`}>
            <ModeIcon mode={r.mode.key} size={13} />
            {r.score}
          </span>
        ))}
      </span>
      <Button variant="ghost" onClick={onOpen}>
        Your progress
        <IconArrowRight size={15} />
      </Button>
    </motion.div>
  );
}

export function RoundPicker({
  system,
  busy,
  recent,
  onPick,
  onLibrary,
}: {
  system: SystemInfo | null;
  busy: boolean;
  recent: SavedSummary[];
  onPick: (mode: Mode) => void;
  onLibrary: () => void;
}) {
  return (
    <>
      <AmbientMesh variant="hero" />
      <Masthead
        subtitle="A mock technical interview that researches the role, adapts to your answers, and reports back in detail."
        onLibrary={system?.storageEnabled ? onLibrary : undefined}
      />
      <Pitch />
      <RecentStrip recent={recent} onOpen={onLibrary} />

      <section>
        <p className={ui.eyebrow}>Choose a round</p>
        <motion.div
          className={s.grid}
          initial="hidden"
          animate="shown"
          variants={stagger(0.05, 0.16)}
        >
          {system?.modes.map((m) => {
            const needsResume = m.key === RESUME_MODE;
            return (
              <motion.button
                key={m.key}
                type="button"
                className={s.card}
                disabled={busy}
                onClick={() => onPick(m)}
                variants={rise}
                // Hover and press are the two states a card has to show,
                // and a transform says both without moving anything else
                // on the page.
                whileHover={busy ? undefined : { y: -4 }}
                whileTap={busy ? undefined : { y: -1, scale: 0.995 }}
                transition={{ type: "spring", stiffness: 400, damping: 28 }}
              >
                <span className={s.cardGlow} aria-hidden="true" />
                <span className={s.cardHead}>
                  <span className={s.glyph}>
                    <ModeIcon mode={m.key} size={20} />
                  </span>
                  <span className={s.nameBlock}>
                    <span className={s.name}>{m.name}</span>
                    <span className={s.role}>
                      {needsResume ? "your own work" : m.defaultRole}
                    </span>
                  </span>
                </span>

                <span className={s.blurb}>{m.blurb}</span>

                <span className={s.cardFoot}>
                  <span className={ui.tagRow}>
                    {m.dims.map((d) => (
                      <span key={d} className={ui.tag}>
                        {d}
                      </span>
                    ))}
                  </span>
                  <span className={s.go}>
                    {needsResume ? "Next" : "Start"}
                    <span className={s.goArrow}>
                      <IconArrowRight size={16} />
                    </span>
                  </span>
                </span>
              </motion.button>
            );
          })}
        </motion.div>
      </section>
    </>
  );
}

/**
 * The one round that needs something from you first.
 *
 * Reached only by picking the résumé round, so the ask always has a reason
 * the candidate has just seen. Drag-and-drop is the convenience; the file
 * input underneath it and the textarea are both complete paths on their
 * own, so nothing here depends on being able to drag.
 */
export function ResumeStep({
  mode,
  resume,
  onResume,
  parsing,
  busy,
  onBack,
  onStart,
  onFile,
}: {
  mode: Mode;
  resume: string;
  onResume: (text: string) => void;
  parsing: boolean;
  busy: boolean;
  onBack: () => void;
  onStart: () => void;
  onFile: (file: File | undefined) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const ready = resume.trim().length > 0;
  const words = resume.trim() ? resume.trim().split(/\s+/).length : 0;

  return (
    <>
      <AmbientMesh />
      <Masthead subtitle="This round runs on your own projects, so it needs them in front of it." />

      <button type="button" className={s.back} onClick={onBack} disabled={busy}>
        <IconArrowLeft size={16} />
        All rounds
      </button>

      <motion.section initial="hidden" animate="shown" variants={stagger()}>
        <motion.p className={ui.eyebrow} variants={rise}>
          {mode.name}
        </motion.p>
        <motion.h2 className={ui.sectionTitle} variants={rise}>
          Add your résumé
        </motion.h2>
        <motion.p className={ui.lede} variants={rise}>
          It is read once, before the first question, and the round is built
          from it: the areas you get asked about are your own projects, and the
          claims worth checking are the ones you made.
        </motion.p>
      </motion.section>

      <motion.div
        className={`${s.drop} ${dragging ? s.dropActive : ""} ${
          ready ? s.dropDone : ""
        }`}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...ease, delay: 0.08 }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onFile(e.dataTransfer.files?.[0]);
        }}
      >
        <input
          type="file"
          accept="application/pdf"
          className={s.dropInput}
          disabled={parsing || busy}
          aria-label="Upload your résumé as a PDF"
          onChange={(e) => onFile(e.target.files?.[0])}
        />
        <span className={s.dropGlyph}>
          {parsing ? (
            <span className={s.dropSpinner} aria-hidden="true" />
          ) : ready ? (
            <IconCheck size={20} />
          ) : (
            <IconSpark size={20} />
          )}
        </span>
        <span className={s.dropTitle}>
          {parsing
            ? "Reading the PDF…"
            : ready
              ? `Read — about ${words} words`
              : "Drop a PDF here, or click to choose"}
        </span>
        <span className={s.dropHint}>
          {ready
            ? "Check it below, then start. You can edit anything that came out wrong."
            : "It gets turned into text you can check and edit below."}
        </span>
      </motion.div>

      <div className={s.field}>
        <label className={s.label} htmlFor="resume">
          Or paste it
        </label>
        <span className={s.help} id="resume-help">
          Projects, skills, education. The more specific your project
          descriptions, the sharper the questions.
        </span>
        <textarea
          id="resume"
          className={s.textarea}
          value={resume}
          disabled={busy}
          aria-describedby="resume-help"
          placeholder={
            "Friday AI — a personal assistant over Gmail and Calendar. FastAPI backend, an LLM agent loop, a sandboxed tool registry…"
          }
          onChange={(e) => onResume(e.target.value)}
        />
      </div>

      <GlassCard className={s.privacy} solid>
        <strong>Where this goes.</strong> It stays in this session and is gone
        when the backend restarts. If you save the finished interview, the
        résumé is kept with it — so you can see which version of your CV
        produced which round.
      </GlassCard>

      <div className={s.actions}>
        <Button
          variant="primary"
          onClick={onStart}
          disabled={!ready || busy || parsing}
        >
          Start the interview
          <IconArrowRight size={16} />
        </Button>
        {!ready && (
          <span className={s.help}>Add your résumé to start this round.</span>
        )}
      </div>
    </>
  );
}
