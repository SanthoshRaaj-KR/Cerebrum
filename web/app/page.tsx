"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./page.module.css";
import {
  Mode,
  SessionState,
  SystemInfo,
  Report,
  extractResume,
  getHealth,
  getReport,
  resetSession,
  startSession,
  submitAnswer,
} from "@/lib/api";
import { MicSession, MicStatus } from "@/lib/webrtc";

type Stage = "setup" | "interview" | "report";

export default function Home() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);

  const [stage, setStage] = useState<Stage>("setup");
  const [mode, setMode] = useState<Mode | null>(null);
  const [role, setRole] = useState("Backend Engineer");
  const [level, setLevel] = useState("Fresher");
  const [resume, setResume] = useState("");
  const [parsing, setParsing] = useState(false);

  const [session, setSession] = useState<SessionState | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [micStatus, setMicStatus] = useState<MicStatus>("idle");
  const [interim, setInterim] = useState("");
  const micRef = useRef<MicSession | null>(null);

  useEffect(() => {
    getHealth()
      .then((data) => setSystem(data.system))
      .catch(() => setBridgeError("Bridge not reachable. Is the backend running?"));
    // Drop the mic if the tab goes away mid-interview.
    return () => micRef.current?.stop();
  }, []);

  const current = session?.turns[session.turns.length - 1] ?? null;
  const awaitingAnswer = !!current && current.answer === null;

  async function handleResumeFile(file: File | undefined) {
    if (!file) return;
    setParsing(true);
    setError(null);
    try {
      const { text } = await extractResume(file);
      setResume(text);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not read that PDF");
    } finally {
      setParsing(false);
    }
  }

  async function handleStart() {
    if (!mode) return;
    setBusy(true);
    setError(null);
    try {
      await resetSession();
      const state = await startSession({ mode: mode.key, role, level, resume });
      setSession(state);
      setReport(null);
      setAnswer("");
      setStage("interview");
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start the interview");
    } finally {
      setBusy(false);
    }
  }

  async function send(skipped: boolean) {
    const text = answer.trim();
    if (!skipped && !text) return;
    stopMic();
    setBusy(true);
    setError(null);
    try {
      const state = await submitAnswer(skipped ? "" : text, skipped);
      setSession(state);
      setAnswer("");
      if (state.finished) await finish();
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not submit that answer");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true);
    try {
      const state = await getReport();
      setSession(state);
      setReport(state.report);
      setStage("report");
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not build the report");
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    stopMic();
    resetSession().catch(() => {});
    setSession(null);
    setReport(null);
    setAnswer("");
    setError(null);
    setStage("setup");
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
      // Deepgram sends finalised chunks as you pause, so append rather
      // than replace - otherwise a long answer keeps overwriting itself.
      onTranscript: (text) =>
        setAnswer((prev) => (prev ? `${prev.trimEnd()} ${text}` : text)),
      onInterim: setInterim,
    });
    micRef.current = mic;
    mic.start();
  }

  // -- setup ---------------------------------------------------------------

  if (stage === "setup") {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <h1>Interview Studio</h1>
          {system && (
            <p className={styles.meta}>
              {system.model} · {system.questionsPerSession} questions ·{" "}
              {system.fresher ? "fresher calibration" : "experienced calibration"}
            </p>
          )}
        </header>

        {bridgeError && <p className={styles.error}>{bridgeError}</p>}
        {error && <p className={styles.error}>{error}</p>}

        <section>
          <h2 className={styles.sectionTitle}>Pick a mode</h2>
          <div className={styles.modeGrid}>
            {system?.modes.map((m) => (
              <button
                key={m.key}
                className={`${styles.modeCard} ${
                  mode?.key === m.key ? styles.modeCardActive : ""
                }`}
                onClick={() => setMode(m)}
              >
                <span className={styles.modeName}>{m.name}</span>
                <span className={styles.modeBlurb}>{m.blurb}</span>
                <span className={styles.dims}>
                  {m.dims.map((d) => (
                    <span key={d} className={styles.dim}>
                      {d}
                    </span>
                  ))}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className={styles.form}>
          <h2 className={styles.sectionTitle}>About you</h2>
          <div className={styles.row}>
            <label className={styles.field}>
              Target role
              <input value={role} onChange={(e) => setRole(e.target.value)} />
            </label>
            <label className={styles.field}>
              Level
              <input value={level} onChange={(e) => setLevel(e.target.value)} />
            </label>
          </div>

          <label className={styles.field}>
            Résumé
            <span className={styles.hint}>
              Paste it, or drop in a PDF. Optional, but the questions get a lot
              more specific with it.
            </span>
            <textarea
              rows={8}
              value={resume}
              placeholder="Projects, skills, education..."
              onChange={(e) => setResume(e.target.value)}
            />
          </label>
          <input
            type="file"
            accept="application/pdf"
            className={styles.file}
            onChange={(e) => handleResumeFile(e.target.files?.[0])}
          />
          {parsing && <p className={styles.hint}>Reading the PDF...</p>}

          <button
            className={styles.primary}
            onClick={handleStart}
            disabled={busy || !mode || !!bridgeError}
          >
            {busy ? "Planning your questions..." : "Start interview"}
          </button>
        </section>
      </div>
    );
  }

  // -- report --------------------------------------------------------------

  if (stage === "report" && session && report) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <h1>{report.headline}</h1>
          <p className={styles.meta}>
            {session.mode.name} · {session.role} · average{" "}
            <strong>{session.average ?? "-"}/10</strong>
          </p>
        </header>

        <section className={styles.dimRow}>
          {session.dimensionAverages.map((d) => (
            <div key={d.name} className={styles.dimCard}>
              <span className={styles.dimScore}>{d.score ?? "-"}</span>
              <span className={styles.dimLabel}>{d.name}</span>
            </div>
          ))}
        </section>

        {report.notes.length > 0 && (
          <section>
            <h2 className={styles.sectionTitle}>What to work on</h2>
            <ul className={styles.notes}>
              {report.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h2 className={styles.sectionTitle}>Transcript</h2>
          {session.turns.map((t) => (
            <article key={t.index} className={styles.reviewTurn}>
              <p className={styles.question}>
                <span className={styles.qNum}>Q{t.index + 1}</span> {t.question}
              </p>
              <p className={styles.answerText}>
                {t.skipped ? <em>skipped</em> : t.answer}
              </p>
              {t.grade && t.grade.score > 0 && (
                <div className={styles.grade}>
                  <span className={styles.score}>{t.grade.score}/10</span>
                  <span>{t.grade.verdict}</span>
                  <p className={styles.gap}>{t.grade.gap}</p>
                </div>
              )}
            </article>
          ))}
        </section>

        <button className={styles.primary} onClick={restart}>
          Take another
        </button>
      </div>
    );
  }

  // -- interview -----------------------------------------------------------

  if (!session) return null;
  const micLive = micStatus === "listening" || micStatus === "connecting";

  return (
    <div className={styles.interview}>
      <aside className={styles.sidebar}>
        <h2 className={styles.sidebarTitle}>{session.mode.name}</h2>
        <ol className={styles.plan}>
          {session.plan.map((p, i) => (
            <li
              key={p.num}
              className={`${styles.slot} ${
                i === session.index ? styles.slotNow : ""
              } ${p.score !== null ? styles.slotDone : ""}`}
            >
              <span className={styles.slotNum}>{p.num}</span>
              <span className={styles.slotLabel}>{p.short}</span>
              {p.score !== null && (
                <span className={styles.slotScore}>{p.score}</span>
              )}
            </li>
          ))}
        </ol>
        {session.average !== null && (
          <p className={styles.average}>
            Average <strong>{session.average}/10</strong>
          </p>
        )}
        <button className={styles.ghost} onClick={restart}>
          End and reset
        </button>
      </aside>

      <main className={styles.main}>
        {error && <p className={styles.error}>{error}</p>}

        {session.turns.map((t) => (
          <article key={t.index} className={styles.turn}>
            <p className={styles.question}>
              <span className={styles.qNum}>
                Q{t.index + 1}/{session.total}
              </span>{" "}
              {t.question}
            </p>
            {t.hint && t.answer === null && (
              <p className={styles.hint}>Hint: {t.hint}</p>
            )}
            {t.answer !== null && (
              <p className={styles.answerText}>
                {t.skipped ? <em>skipped</em> : t.answer}
              </p>
            )}
            {t.grade && t.grade.score > 0 && (
              <div className={styles.grade}>
                <div className={styles.gradeHead}>
                  <span className={styles.score}>{t.grade.score}/10</span>
                  <span>{t.grade.verdict}</span>
                </div>
                <div className={styles.rubric}>
                  {t.grade.rubric.map((r) => (
                    <span key={r.name} className={styles.rubricItem}>
                      {r.name} <strong>{r.score}</strong>
                    </span>
                  ))}
                </div>
                {t.grade.strength && (
                  <p className={styles.worked}>Worked: {t.grade.strength}</p>
                )}
                {t.grade.gap && <p className={styles.gap}>Missing: {t.grade.gap}</p>}
              </div>
            )}
          </article>
        ))}

        {awaitingAnswer && (
          <div className={styles.composer}>
            <textarea
              rows={5}
              value={answer}
              disabled={busy}
              placeholder="Your answer... (Ctrl+Enter to submit)"
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(false);
              }}
            />
            {micLive && (
              <p className={styles.interim}>
                {interim || "listening..."}
              </p>
            )}
            <div className={styles.composerBar}>
              <button
                className={`${styles.mic} ${micLive ? styles.micLive : ""}`}
                onClick={toggleMic}
                disabled={busy}
                title="Dictate your answer"
              >
                {micStatus === "connecting"
                  ? "connecting..."
                  : micStatus === "listening"
                    ? "listening - click to stop"
                    : "Dictate"}
              </button>
              <span className={styles.spacer} />
              <button
                className={styles.ghost}
                onClick={() => send(true)}
                disabled={busy}
              >
                Skip
              </button>
              <button
                className={styles.primary}
                onClick={() => send(false)}
                disabled={busy || !answer.trim()}
              >
                {busy ? "Grading..." : "Submit"}
              </button>
            </div>
          </div>
        )}

        {busy && !awaitingAnswer && <p className={styles.hint}>Working...</p>}
      </main>
    </div>
  );
}
