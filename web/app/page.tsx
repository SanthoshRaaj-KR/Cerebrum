"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./page.module.css";
import {
  Clock,
  Mode,
  SessionState,
  SystemInfo,
  Scorecard,
  extractResume,
  getHealth,
  getReport,
  resetSession,
  startSession,
  submitAnswer,
} from "@/lib/api";
import { MicSession, MicStatus } from "@/lib/webrtc";

type Stage = "setup" | "interview" | "report";

// Mirrors clock.py's phase boundaries, so the countdown and phase label
// keep ticking smoothly between the answers that actually refresh `clock`
// from the backend, instead of freezing until the next response arrives.
const OPENING_END = 0.12;
const CORE_END = 0.6;
const DEPTH_END = 0.88;

const PHASE_LABEL: Record<Clock["phase"], string> = {
  opening: "Opening",
  core: "Core",
  depth: "Depth",
  closing: "Closing",
};

function livePhase(fraction: number): Clock["phase"] {
  if (fraction < OPENING_END) return "opening";
  if (fraction < CORE_END) return "core";
  if (fraction < DEPTH_END) return "depth";
  return "closing";
}

function formatClock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const rest = s % 60;
  return `${m}:${rest.toString().padStart(2, "0")}`;
}

const VERDICT_LABEL: Record<Scorecard["verdict"], string> = {
  strong_yes: "Strong yes",
  yes: "Yes",
  borderline: "Borderline",
  not_yet: "Not yet",
};

const STATUS_LABEL: Record<Scorecard["competencies"][number]["status"], string> = {
  solid: "Solid",
  developing: "Developing",
  not_shown: "Not shown",
  not_covered: "Not covered",
};

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
  const [report, setReport] = useState<Scorecard | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [micStatus, setMicStatus] = useState<MicStatus>("idle");
  const [interim, setInterim] = useState("");
  const micRef = useRef<MicSession | null>(null);

  // Ticks once a second while an interview is live, so the countdown moves
  // smoothly between the answers that actually refresh `clock` from the
  // backend rather than jumping only when a request completes.
  const [now, setNow] = useState(() => Date.now() / 1000);

  useEffect(() => {
    getHealth()
      .then((data) => setSystem(data.system))
      .catch(() => setBridgeError("Bridge not reachable. Is the backend running?"));
    // Drop the mic if the tab goes away mid-interview.
    return () => micRef.current?.stop();
  }, []);

  useEffect(() => {
    if (stage !== "interview") return;
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [stage]);

  const current = session?.turns[session.turns.length - 1] ?? null;
  const awaitingAnswer = !!current && current.answer === null;

  const clock = session?.clock ?? null;
  const elapsed = clock ? Math.max(0, now - clock.startedAt) : 0;
  const remaining = clock ? Math.max(0, clock.durationSeconds - elapsed) : 0;
  const fraction = clock && clock.durationSeconds > 0 ? Math.min(1, elapsed / clock.durationSeconds) : 0;
  const phase = clock ? livePhase(fraction) : "opening";

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
      setNow(Date.now() / 1000);
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
      setReport(state.scorecard);
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
          <h1>Threshold</h1>
          {system && (
            <p className={styles.meta}>
              {system.model} · {system.durationMinutes}-minute interview ·{" "}
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
              <span className={styles.hint}>
                Drives the research - what this role&apos;s interviews actually
                cover gets looked up before you start.
              </span>
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
            {busy ? `Reading up on ${role || "this role"}'s interviews...` : "Start interview"}
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
            {session.mode.name} · {session.role}
          </p>
        </header>

        <section className={styles.verdictRow}>
          <div className={styles.verdictCard}>
            <span className={styles.verdictScore}>{report.score}/10</span>
            <span className={`${styles.verdictBadge} ${styles[`verdict_${report.verdict}`]}`}>
              {VERDICT_LABEL[report.verdict]}
            </span>
          </div>
          {!report.grounded && (
            <p className={styles.hint}>
              Research wasn&apos;t available for this session - this scorecard is
              based on the model&apos;s own knowledge of the role, not a live search.
            </p>
          )}
        </section>

        <section>
          <h2 className={styles.sectionTitle}>What a fresher for this role needs</h2>
          <div className={styles.competencyTable}>
            {report.competencies.map((c) => (
              <div key={c.name} className={styles.competencyRow}>
                <span
                  className={`${styles.statusBadge} ${styles[`status_${c.status}`]}`}
                >
                  {STATUS_LABEL[c.status]}
                </span>
                <div className={styles.competencyBody}>
                  <span className={styles.competencyName}>{c.name}</span>
                  {c.evidence && (
                    <span className={styles.competencyEvidence}>{c.evidence}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>

        {report.strengths.length > 0 && (
          <section>
            <h2 className={styles.sectionTitle}>Strengths</h2>
            <ul className={styles.notes}>
              {report.strengths.map((s, i) => (
                <li key={i} className={styles.strengthNote}>
                  {s}
                </li>
              ))}
            </ul>
          </section>
        )}

        {report.gaps.length > 0 && (
          <section>
            <h2 className={styles.sectionTitle}>Gaps</h2>
            <ul className={styles.notes}>
              {report.gaps.map((g, i) => (
                <li key={i}>{g}</li>
              ))}
            </ul>
          </section>
        )}

        {report.notes.length > 0 && (
          <section>
            <h2 className={styles.sectionTitle}>Coach notes</h2>
            <ul className={styles.notes}>
              {report.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </section>
        )}

        {report.sources.length > 0 && (
          <section>
            <h2 className={styles.sectionTitle}>Researched from</h2>
            <ul className={styles.sourceList}>
              {report.sources.map((s) => (
                <li key={s}>
                  <a href={s} target="_blank" rel="noreferrer">
                    {s}
                  </a>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section>
          <h2 className={styles.sectionTitle}>Transcript</h2>
          {session.turns.map((t, i) => (
            <article key={i} className={styles.reviewTurn}>
              <p className={styles.question}>{t.question}</p>
              <p className={styles.answerText}>
                {t.skipped ? <em>skipped</em> : t.answer}
              </p>
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

        <div className={styles.clockBlock}>
          <span className={styles.clockTime}>{formatClock(remaining)}</span>
          <span className={styles.clockPhase}>{PHASE_LABEL[phase]}</span>
          <div className={styles.clockTrack}>
            <div
              className={styles.clockFill}
              style={{ width: `${Math.round(fraction * 100)}%` }}
            />
          </div>
        </div>

        {session.researchBrief && session.researchBrief.competencies.length > 0 && (
          <div className={styles.briefBlock}>
            <span className={styles.hint}>Covering</span>
            <ul className={styles.competencyList}>
              {session.researchBrief.competencies.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        )}

        <span className={styles.spacer} />
        <button className={styles.ghost} onClick={finish} disabled={busy}>
          End interview
        </button>
        <button className={styles.ghost} onClick={restart}>
          Reset
        </button>
      </aside>

      <main className={styles.main}>
        {error && <p className={styles.error}>{error}</p>}

        {session.turns.map((t, i) => (
          <article key={i} className={styles.turn}>
            <p className={styles.question}>{t.question}</p>
            {t.answer !== null && (
              <p className={styles.answerText}>
                {t.skipped ? <em>skipped</em> : t.answer}
              </p>
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
                {busy ? "..." : "Submit"}
              </button>
            </div>
          </div>
        )}

        {busy && !awaitingAnswer && <p className={styles.hint}>Working...</p>}
      </main>
    </div>
  );
}
