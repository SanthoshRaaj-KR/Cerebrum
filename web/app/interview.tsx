"use client";

/**
 * The interview.
 *
 * One question at a time and nothing else competing with it. Answered
 * turns stay on the page but recede - they are context, and at full
 * strength the live question ends up competing with its own history.
 *
 * Nothing evaluative appears here, ever. No score, no running tally, no
 * indication of how the last answer landed. The interviewer is forming a
 * view every turn and showing any of it would poison the rest of the
 * interview, which is the same reason the backend keeps the judge and the
 * speaker as separate calls. The constellation in the bar is the closest
 * this screen comes, and it says only *asked about* - see constellation.tsx.
 *
 * The one number on screen is progress through the question budget, and
 * the copy is careful that it is an estimate rather than a countdown.
 *
 * On motion: the live question types itself in, which is the one piece of
 * theatre on this screen and earns its place - it puts the question on the
 * page at reading speed, so you arrive at the end of it having read it
 * rather than having skipped to the last clause. It is skippable, it
 * finishes instantly on a click, and under reduced motion it never runs.
 */

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { SessionState } from "@/lib/api";
import { MicStatus } from "@/lib/webrtc";
import { Constellation } from "./constellation";
import { IconArrowRight, IconMic, ModeIcon } from "./icons";
import { AmbientMesh } from "./mesh";
import { rise, stagger } from "./motion";
import { Button, Meter, ThemeToggle, ui } from "./ui";
import { ThinkingTurn } from "./waiting";
import s from "./interview.module.css";

/**
 * Types a question out at reading pace.
 *
 * Per character rather than per word: word-by-word reveals read as a
 * stutter at this size. 14ms is fast enough that a long question does not
 * become a wait - about 70 characters a second, comfortably quicker than
 * anyone reads - and the whole thing can be skipped by clicking it.
 */
function Typewriter({ text }: { text: string }) {
  const reduced = useReducedMotion();
  const [typed, setTyped] = useState(0);

  // Derived rather than stored, so reduced motion needs no state write and
  // therefore no cascading render: the full question is simply what
  // renders. The counter only ever advances from the interval below.
  const shown = reduced ? text.length : typed;
  const done = shown >= text.length;

  useEffect(() => {
    if (reduced) return;
    let i = 0;
    const id = setInterval(() => {
      i += 2;                       // two characters a tick: smooth, and half the timers
      setTyped(i);
      if (i >= text.length) clearInterval(id);
    }, 14);
    return () => clearInterval(id);
  }, [text, reduced]);

  return (
    <p
      className={s.question}
      onClick={() => setTyped(text.length)}
      // The full question is in the DOM for assistive tech from the first
      // frame; only the visual reveal is progressive. Announcing it one
      // character at a time would be unusable.
      aria-label={text}
    >
      <span aria-hidden="true">
        {text.slice(0, shown)}
        {!done && <span className={s.caret} />}
      </span>
      <span className="srOnly">{text}</span>
    </p>
  );
}

export function InterviewScreen({
  session,
  answer,
  onAnswer,
  busy,
  thinking,
  error,
  micStatus,
  interim,
  onToggleMic,
  onSubmit,
  onSkip,
  onEnd,
  pending,
}: {
  session: SessionState;
  answer: string;
  onAnswer: (text: string) => void;
  busy: boolean;
  thinking: boolean;
  error: string | null;
  micStatus: MicStatus;
  interim: string;
  onToggleMic: () => void;
  onSubmit: () => void;
  onSkip: () => void;
  onEnd: () => void;
  pending: { text: string; skipped: boolean } | null;
}) {
  const { pacing } = session;
  const turns = session.turns;
  const current = turns[turns.length - 1] ?? null;
  const awaiting = !!current && current.answer === null && !busy;
  const micLive = micStatus === "listening" || micStatus === "connecting";
  const endRef = useRef<HTMLDivElement | null>(null);

  // Keep the live question in view as the conversation grows. Under
  // reduced-motion the global rule turns this into a jump, which is the
  // correct behaviour rather than a degraded one.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, thinking]);

  const competencies = session.researchBrief?.competencies ?? [];

  return (
    <div className={s.shell}>
      <AmbientMesh />
      {/* The round name is the page's heading. It is drawn in the bar at
          label size, so the real h1 is here and hidden - a page with no h1
          leaves anyone navigating by heading with nothing to land on. */}
      <h1 className="srOnly">{session.mode.name} interview</h1>
      <div className={s.bar}>
        <div className={s.barInner}>
          <span className={s.barTitle}>
            <span className={s.barGlyph}>
              <ModeIcon mode={session.mode.key} size={18} />
            </span>
            <span>{session.mode.name}</span>
          </span>

          <div className={s.barMeter}>
            <Meter
              asked={pacing.questionsAsked}
              planned={pacing.plannedQuestions}
              closing={pacing.closing}
              note={
                pacing.closing
                  ? "last question"
                  : `~${pacing.estimatedMinutes} min`
              }
            />
          </div>

          <div className={s.barActions}>
            <ThemeToggle />
            <Button variant="ghost" onClick={onEnd} disabled={busy}>
              End
            </Button>
          </div>
        </div>
      </div>

      <main className={s.stream}>
        {error && <p className={`${ui.notice} ${ui.noticeBad}`}>{error}</p>}

        {/* The plan, shown once - before the first answer, then gone. It
            answers "what have I sat down to" without becoming furniture. */}
        <AnimatePresence>
          {turns.length === 1 &&
            !current?.answer &&
            pacing.competencyCount > 0 && (
              <motion.div
                key="plan"
                className={s.plan}
                initial="hidden"
                animate="shown"
                exit={{ opacity: 0, y: -8 }}
                variants={stagger(0.05)}
              >
                <motion.div className={s.planMain} variants={rise}>
                  <p className={s.planTitle}>What this round covers</p>
                  <p className={s.planLine}>
                    About {pacing.plannedQuestions} questions, roughly{" "}
                    {pacing.estimatedMinutes} minutes. It ends when every area
                    below has been covered, so the exact number moves with your
                    answers. Answer one well and the next on that area gets
                    harder.
                  </p>
                  {session.researchBrief && (
                    <ul className={s.planList}>
                      {session.researchBrief.competencies.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  )}
                </motion.div>
                {competencies.length >= 3 && (
                  <motion.div variants={rise} className={s.planViz}>
                    <Constellation
                      competencies={competencies}
                      asked={pacing.questionsAsked}
                      closing={pacing.closing}
                    />
                  </motion.div>
                )}
              </motion.div>
            )}
        </AnimatePresence>

        {turns.map((t, i) => {
          const last = i === turns.length - 1;
          const shown =
            t.answer !== null
              ? { text: t.answer, skipped: t.skipped }
              : last && pending
                ? pending
                : null;
          const live = last && !shown;

          return (
            <motion.article
              key={i}
              className={`${s.turn} ${live ? "" : s.turnPast}`}
              initial={live ? { opacity: 0, y: 16 } : false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
              // The live turn gets a layout animation so that when it
              // recedes into history the card travels rather than cutting.
              layout="position"
            >
              <p className={s.who}>Interviewer</p>
              {live ? (
                <Typewriter text={t.question} />
              ) : (
                <p className={s.question}>{t.question}</p>
              )}
              {shown && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.3 }}
                >
                  <p className={s.who}>You</p>
                  <p className={s.answer}>
                    {shown.skipped ? (
                      <span className={s.skipped}>skipped</span>
                    ) : (
                      shown.text
                    )}
                  </p>
                </motion.div>
              )}
            </motion.article>
          );
        })}

        <AnimatePresence>{thinking && <ThinkingTurn />}</AnimatePresence>
        <div ref={endRef} />
      </main>

      <AnimatePresence>
        {awaiting && (
          <motion.div
            className={s.composer}
            initial={{ y: 24, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className={s.composerInner}>
              <label className="srOnly" htmlFor="answer">
                Your answer
              </label>
              <textarea
                id="answer"
                className={s.input}
                value={answer}
                disabled={busy}
                placeholder="Think out loud — how you got there counts for as much as the answer."
                onChange={(e) => onAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) onSubmit();
                }}
              />
              {micLive && (
                <p className={s.interim} aria-live="polite">
                  {interim || "Listening…"}
                </p>
              )}
              <div className={s.bar2}>
                <Button
                  variant="secondary"
                  className={micLive ? s.micLive : ""}
                  onClick={onToggleMic}
                  disabled={busy}
                >
                  <IconMic size={16} />
                  {micStatus === "connecting"
                    ? "Connecting…"
                    : micLive
                      ? "Stop"
                      : "Dictate"}
                </Button>
                <span className={s.hintKeys}>Ctrl + Enter to send</span>
                <span className={s.spacer} />
                <Button variant="ghost" onClick={onSkip} disabled={busy}>
                  Skip
                </Button>
                <Button
                  variant="primary"
                  onClick={onSubmit}
                  disabled={busy || !answer.trim()}
                >
                  Send
                  <IconArrowRight size={16} />
                </Button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
