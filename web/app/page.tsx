"use client";

/**
 * The console.
 *
 * This file owns the state machine and the calls to the bridge; every
 * screen is its own component. Four stages:
 *
 *   rounds  -> pick one. For five of the six, that starts the interview.
 *   resume  -> only ever reached by picking the résumé round, which needs
 *              a CV because a CV is that round's entire syllabus.
 *   interview
 *   report
 *
 * Nothing is asked for that a round will not use. The round is the role,
 * the level comes from config, and the résumé is requested exactly once,
 * in the one place it matters.
 */

import { useEffect, useRef, useState } from "react";
import {
  Mode,
  Scorecard,
  SessionState,
  SystemInfo,
  extractResume,
  getHealth,
  getReport,
  resetSession,
  startSession,
  submitAnswer,
} from "@/lib/api";
import { MicSession, MicStatus } from "@/lib/webrtc";
import { InterviewScreen } from "./interview";
import { ReportScreen } from "./report";
import { ResumeStep, RoundPicker } from "./rounds";
import { BuildingReport, StartingUp } from "./waiting";
import { ui } from "./ui";

type Stage = "rounds" | "resume" | "interview" | "report";

const RESUME_MODE = "resume_projects";

export default function Home() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);

  const [stage, setStage] = useState<Stage>("rounds");
  const [mode, setMode] = useState<Mode | null>(null);
  const [resume, setResume] = useState("");
  const [parsing, setParsing] = useState(false);

  const [session, setSession] = useState<SessionState | null>(null);
  const [report, setReport] = useState<Scorecard | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [starting, setStarting] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [pending, setPending] = useState<{
    text: string;
    skipped: boolean;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [micStatus, setMicStatus] = useState<MicStatus>("idle");
  const [interim, setInterim] = useState("");
  const micRef = useRef<MicSession | null>(null);

  useEffect(() => {
    getHealth()
      .then((d) => setSystem(d.system))
      .catch(() =>
        setBridgeError(
          "Can't reach the backend. Start it with ./start.sh (or .\\start.ps1) and reload."
        )
      );
    return () => micRef.current?.stop();
  }, []);

  /** Picking a round. Five of six go straight into the interview; only the
   * résumé round has anything left to ask for. */
  function pickRound(m: Mode) {
    setMode(m);
    setError(null);
    if (m.key === RESUME_MODE) {
      setStage("resume");
      return;
    }
    void begin(m, "");
  }

  async function begin(m: Mode, resumeText: string) {
    setBusy(true);
    setStarting(true);
    setError(null);
    try {
      await resetSession();
      const state = await startSession({ mode: m.key, resume: resumeText });
      setSession(state);
      setReport(null);
      setAnswer("");
      setPending(null);
      setStage("interview");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't start the interview."
      );
      // Stay where they were rather than stranding them on a blank screen.
      setStage(m.key === RESUME_MODE ? "resume" : "rounds");
    } finally {
      setBusy(false);
      setStarting(false);
    }
  }

  async function handleFile(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("That needs to be a PDF — or paste the text instead.");
      return;
    }
    setParsing(true);
    setError(null);
    try {
      const { text } = await extractResume(file);
      setResume(text);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't read that PDF."
      );
    } finally {
      setParsing(false);
    }
  }

  async function send(skipped: boolean) {
    const text = answer.trim();
    if (!skipped && !text) return;
    stopMic();
    setBusy(true);
    setError(null);
    setPending({ text, skipped });
    try {
      const state = await submitAnswer(skipped ? "" : text, skipped);
      setSession(state);
      setAnswer("");
      setPending(null);
      if (state.finished) await finish();
    } catch (err) {
      // Their typed answer stays in the box - losing a long one to a blip
      // is not something anyone should have to retype from memory.
      setPending(null);
      setError(
        err instanceof Error ? err.message : "Couldn't send that answer."
      );
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true);
    setFinishing(true);
    try {
      const state = await getReport();
      setSession(state);
      setReport(state.scorecard);
      setStage("report");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't build the report."
      );
    } finally {
      setBusy(false);
      setFinishing(false);
    }
  }

  function restart() {
    stopMic();
    void resetSession().catch(() => {});
    setSession(null);
    setReport(null);
    setAnswer("");
    setPending(null);
    setError(null);
    setMode(null);
    setFinishing(false);
    setStage("rounds");
  }

  function stopMic() {
    micRef.current?.stop();
    micRef.current = null;
    setInterim("");
  }

  function toggleMic() {
    if (micStatus === "connecting" || micStatus === "listening") {
      stopMic();
      return;
    }
    setError(null);
    const mic = new MicSession({
      onStatusChange: setMicStatus,
      onError: setError,
      // Deepgram finalises a chunk each time you pause, so append rather
      // than replace - otherwise a long answer overwrites itself.
      onTranscript: (t) =>
        setAnswer((prev) => (prev ? `${prev.trimEnd()} ${t}` : t)),
      onInterim: setInterim,
    });
    micRef.current = mic;
    mic.start();
  }

  // -- waiting ------------------------------------------------------------

  if (starting && mode) {
    const resumeRound = mode.key === RESUME_MODE;
    return (
      <div className={ui.page}>
        <StartingUp
          title={mode.name}
          steps={
            resumeRound
              ? [
                  "Reading your résumé",
                  "Working out what your own projects make it fair to examine",
                  "Writing the opening question",
                ]
              : [
                  `Searching what ${mode.defaultRole} interviews are asking right now`,
                  "Distilling that into the areas this round will cover",
                  "Writing the opening question",
                ]
          }
          note="Usually fifteen to thirty seconds, and only once — every question after this one comes back much faster."
        />
      </div>
    );
  }

  if (finishing && session) {
    return (
      <div className={ui.page}>
        <BuildingReport
          title={session.mode.name}
          count={session.turns.length}
        />
      </div>
    );
  }

  // -- screens ------------------------------------------------------------

  if (stage === "report" && session && report) {
    return (
      <ReportScreen
        session={session}
        report={report}
        system={system}
        onRestart={restart}
      />
    );
  }

  if (stage === "interview" && session) {
    return (
      <InterviewScreen
        session={session}
        answer={answer}
        onAnswer={setAnswer}
        busy={busy}
        thinking={busy && !finishing}
        error={error}
        micStatus={micStatus}
        interim={interim}
        onToggleMic={toggleMic}
        onSubmit={() => send(false)}
        onSkip={() => send(true)}
        onEnd={finish}
        pending={pending}
      />
    );
  }

  if (stage === "resume" && mode) {
    return (
      <div className={ui.page}>
        {error && <p className={`${ui.notice} ${ui.noticeBad}`}>{error}</p>}
        <ResumeStep
          mode={mode}
          resume={resume}
          onResume={setResume}
          parsing={parsing}
          busy={busy}
          onBack={() => {
            setMode(null);
            setError(null);
            setStage("rounds");
          }}
          onStart={() => begin(mode, resume)}
          onFile={handleFile}
        />
      </div>
    );
  }

  return (
    <div className={ui.page}>
      {bridgeError && (
        <p className={`${ui.notice} ${ui.noticeBad}`}>{bridgeError}</p>
      )}
      {error && <p className={`${ui.notice} ${ui.noticeBad}`}>{error}</p>}
      <RoundPicker
        system={system}
        busy={busy || !!bridgeError}
        onPick={pickRound}
      />
    </div>
  );
}
