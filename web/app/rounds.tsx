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
 */

import { useState } from "react";
import { Mode, SystemInfo } from "@/lib/api";
import { IconArrowLeft, IconArrowRight, ModeIcon } from "./icons";
import { Button, ThemeToggle, ui } from "./ui";
import s from "./rounds.module.css";

const RESUME_MODE = "resume_projects";

function Masthead({ subtitle }: { subtitle: string }) {
  return (
    <header className={s.masthead}>
      <div>
        <h1 className={s.wordmark}>Cerebrum</h1>
        <p className={s.tagline}>{subtitle}</p>
      </div>
      <ThemeToggle />
    </header>
  );
}

export function RoundPicker({
  system,
  busy,
  onPick,
}: {
  system: SystemInfo | null;
  busy: boolean;
  onPick: (mode: Mode) => void;
}) {
  return (
    <>
      <Masthead subtitle="Pick a round. It researches what that role is actually being asked right now, then adapts to how you answer." />

      <section>
        <p className={ui.eyebrow}>Choose a round</p>
        <div className={s.grid}>
          {system?.modes.map((m) => {
            const needsResume = m.key === RESUME_MODE;
            return (
              <button
                key={m.key}
                type="button"
                className={s.card}
                disabled={busy}
                onClick={() => onPick(m)}
              >
                <span className={s.cardHead}>
                  <span className={s.glyph}>
                    <ModeIcon mode={m.key} size={20} />
                  </span>
                  <span>
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
              </button>
            );
          })}
        </div>
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

  return (
    <>
      <Masthead subtitle="This round runs on your own projects, so it needs them in front of it." />

      <button type="button" className={s.back} onClick={onBack} disabled={busy}>
        <IconArrowLeft size={16} />
        All rounds
      </button>

      <section>
        <p className={ui.eyebrow}>{mode.name}</p>
        <h2 className={ui.sectionTitle}>Add your résumé</h2>
        <p className={ui.lede}>
          It is read once, before the first question, and the round is built
          from it: the areas you get asked about are your own projects, and the
          claims worth checking are the ones you made. Nothing is stored — it
          lives in this session and goes when the backend restarts.
        </p>
      </section>

      <div
        className={`${s.drop} ${dragging ? s.dropActive : ""}`}
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
        <span className={s.dropTitle}>
          {parsing ? "Reading the PDF…" : "Drop a PDF here, or click to choose"}
        </span>
        <span className={s.dropHint}>
          It gets turned into text you can check and edit below.
        </span>
      </div>

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

      <div className={s.actions}>
        <Button variant="primary" onClick={onStart} disabled={!ready || busy || parsing}>
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
