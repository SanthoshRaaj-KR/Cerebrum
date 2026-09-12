"use client";

/**
 * The console.
 *
 * This file owns the state machine and the calls to the bridge; every
 * screen is its own component. Six stages:
 *
 *   rounds    -> pick one. For five of the six, that starts the interview.
 *   resume    -> only ever reached by picking the résumé round, which needs
 *                a CV because a CV is that round's entire syllabus.
 *   interview
 *   report    -> the live one, with the option to keep it
 *   library   -> everything kept, and whether you are getting better
 *   archive   -> one kept interview, read back
 *
 * Nothing is asked for that a round will not use. The round is the role,
 * the level comes from config, and the résumé is requested exactly once,
 * in the one place it matters.
 *
 * `report` and `archive` render the same component from the same
 * `ReportView`. Two report screens would drift, and the saved one - the
 * one you come back to months later - would be the one that rotted.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Mode,
  SavedSummary,
  Scorecard,
  SessionState,
  SystemInfo,
  extractResume,
  getHealth,
  getInterview,
  getReport,
  listInterviews,
  resetSession,
  saveInterview,
  startSession,
  submitAnswer,
} from "@/lib/api";
import { MicSession, MicStatus } from "@/lib/webrtc";
import { InterviewScreen } from "./interview";
import { LibraryScreen } from "./library";
import { AmbientMesh } from "./mesh";
import { ReportScreen, ReportView } from "./report";
import { ResumeStep, RoundPicker } from "./rounds";
import { BuildingReport, StartingUp } from "./waiting";
import { Toast, ui } from "./ui";

type Stage = "rounds" | "resume" | "interview" | "report" | "library" | "archive";

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

  // Saved interviews.
  const [recent, setRecent] = useState<SavedSummary[]>([]);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const [archive, setArchive] = useState<ReportView | null>(null);
  const [toast, setToast] = useState<{ text: string; tone: "ok" | "bad" } | null>(
    null
  );

  const [micStatus, setMicStatus] = useState<MicStatus>("idle");
  const [interim, setInterim] = useState("");
  const micRef = useRef<MicSession | null>(null);

  const storageEnabled = !!system?.storageEnabled;

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

  /** The strip of recent scores on the rounds screen. Best-effort: a
   * database that is down should never stop you taking an interview. */
  const refreshRecent = useCallback(() => {
    if (!storageEnabled) return;
    listInterviews()
      .then((d) => setRecent(d.interviews))
      .catch(() => {});
  }, [storageEnabled]);

  useEffect(refreshRecent, [refreshRecent]);

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
      setSaveState("idle");
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
      setError(err instanceof Error ? err.message : "Couldn't read that PDF.");
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
      setError(err instanceof Error ? err.message : "Couldn't send that answer.");
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
      setSaveState("idle");
      setStage("report");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't build the report.");
    } finally {
      setBusy(false);
      setFinishing(false);
    }
  }

  /** Keeping the interview. Explicit, and only ever after the report - the
   * bridge refuses anything else. */
  async function keep() {
    if (saveState !== "idle") return;
    setSaveState("saving");
    try {
      await saveInterview();
      setSaveState("saved");
      setToast({ text: "Kept. It's in your library.", tone: "ok" });
      refreshRecent();
    } catch (err) {
      setSaveState("idle");
      setToast({
        text: err instanceof Error ? err.message : "Couldn't save that.",
        tone: "bad",
      });
    }
  }

  async function openSaved(id: string) {
    setBusy(true);
    try {
      const doc = await getInterview(id);
      setArchive({
        mode: doc.mode,
        role: doc.role,
        questionCount: doc.questionCount,
        savedAt: doc.savedAt,
        card: {
          verdict: doc.verdict,
          score: doc.score,
          headline: doc.headline,
          strengths: doc.strengths,
          gaps: doc.gaps,
          notes: doc.notes,
          competencies: doc.competencies,
          sources: doc.sources,
          grounded: doc.grounded,
          answers: doc.answers,
        },
        provenance: doc.system.scorerModel
          ? { scorerModel: doc.system.scorerModel }
          : null,
      });
      setStage("archive");
      window.scrollTo({ top: 0 });
    } catch (err) {
      setToast({
        text: err instanceof Error ? err.message : "Couldn't open that one.",
        tone: "bad",
      });
    } finally {
      setBusy(false);
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
    setArchive(null);
    setSaveState("idle");
    setStage("rounds");
    refreshRecent();
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

  const toastEl = (
    <Toast
      message={toast?.text ?? null}
      tone={toast?.tone ?? "ok"}
      onDone={() => setToast(null)}
    />
  );

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
        <BuildingReport title={session.mode.name} count={session.turns.length} />
      </div>
    );
  }

  // -- screens ------------------------------------------------------------

  if (stage === "archive" && archive) {
    return (
      <>
        <ReportScreen
          view={archive}
          onRestart={() => {
            setArchive(null);
            setStage("library");
          }}
          backLabel="Back to your library"
        />
        {toastEl}
      </>
    );
  }

  if (stage === "library") {
    return (
      <>
        <LibraryScreen
          storageEnabled={storageEnabled}
          onBack={() => setStage("rounds")}
          onOpen={openSaved}
        />
        {toastEl}
      </>
    );
  }

  if (stage === "report" && session && report) {
    return (
      <>
        <ReportScreen
          view={{
            mode: session.mode,
            role: session.role,
            questionCount: session.turns.length,
            card: report,
            provenance: system
              ? {
                  scorerModel: system.scorerModel,
                  doubleCheckWrong: system.doubleCheckWrong,
                }
              : null,
          }}
          onRestart={restart}
          onSave={keep}
          saveState={saveState}
          storageEnabled={storageEnabled}
        />
        {toastEl}
      </>
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
      <main className={ui.page}>
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
      </main>
    );
  }

  return (
    <>
      <AmbientMesh variant="hero" />
      <main className={ui.page}>
        {bridgeError && (
          <p className={`${ui.notice} ${ui.noticeBad}`}>{bridgeError}</p>
        )}
        {error && <p className={`${ui.notice} ${ui.noticeBad}`}>{error}</p>}
        <RoundPicker
          system={system}
          busy={busy || !!bridgeError}
          recent={recent}
          onPick={pickRound}
          onLibrary={() => setStage("library")}
        />
      </main>
      {toastEl}
    </>
  );
}
