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
 * speaker as separate calls.
 *
 * The one number on screen is progress through the question budget, and
 * the copy is careful that it is an estimate rather than a countdown.
 */

import { useEffect, useRef } from "react";
import { SessionState } from "@/lib/api";
import { MicStatus } from "@/lib/webrtc";
import { IconArrowRight, IconMic, ModeIcon } from "./icons";
import { Button, Meter, ThemeToggle, ui } from "./ui";
import { ThinkingTurn } from "./waiting";
import s from "./interview.module.css";

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

  return (
    <div className={s.shell}>
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
        {turns.length === 1 && !current?.answer && pacing.competencyCount > 0 && (
          <div className={s.plan}>
            <p className={s.planTitle}>What this round covers</p>
            <p className={s.planLine}>
              About {pacing.plannedQuestions} questions, roughly{" "}
              {pacing.estimatedMinutes} minutes. It ends when every area below
              has been covered, so the exact number moves with your answers.
              Answer one well and the next on that area gets harder.
            </p>
            {session.researchBrief && (
              <ul className={s.planList}>
                {session.researchBrief.competencies.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {turns.map((t, i) => {
          const last = i === turns.length - 1;
          const shown =
            t.answer !== null
              ? { text: t.answer, skipped: t.skipped }
              : last && pending
                ? pending
                : null;
          return (
            <article
              key={i}
              className={`${s.turn} ${last && !shown ? "" : s.turnPast}`}
            >
              <p className={s.who}>Interviewer</p>
              <p className={s.question}>{t.question}</p>
              {shown && (
                <>
                  <p className={s.who}>You</p>
                  <p className={s.answer}>
                    {shown.skipped ? (
                      <span className={s.skipped}>skipped</span>
                    ) : (
                      shown.text
                    )}
                  </p>
                </>
              )}
            </article>
          );
        })}

        {thinking && <ThinkingTurn />}
        <div ref={endRef} />
      </main>

      {awaiting && (
        <div className={s.composer}>
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
        </div>
      )}
    </div>
  );
}
