"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./page.module.css";
import {
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
import { Pipeline, PipelineCompact } from "./pipeline";
import { BuildingReport, Dots, StartingUp, ThinkingTurn } from "./waiting";

type Stage = "setup" | "interview" | "report";

/** The one round with no external role to research - see gateway.py. */
const RESUME_MODE = "resume_projects";

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
  const [role, setRole] = useState("");
  const [level, setLevel] = useState("Fresher");
  const [resume, setResume] = useState("");
  const [parsing, setParsing] = useState(false);
  // Once they edit the role themselves it is theirs - picking a different
  // round must not quietly overwrite what they typed.
  const roleEdited = useRef(false);

  const [session, setSession] = useState<SessionState | null>(null);
  const [report, setReport] = useState<Scorecard | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  // Distinct from `busy`: the wait for the scorecard is a different wait to
  // the one between questions, and says a different thing. On the "End
  // interview" path the session isn't flagged finished until the response
  // lands, so it can't be inferred from the session.
  const [finishing, setFinishing] = useState(false);
  // What they just submitted, held only until the server echoes it back in
  // the turn list. Without it the composer closes, the turn has no answer
  // on it yet, and their own words vanish off the screen while they wait.
  const [pending, setPending] = useState<{ text: string; skipped: boolean } | null>(
    null
  );
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

  /** Picking a round fills in the role it implies, so the next step is a
   * confirmation rather than a re-ask - and so choosing "AI Engineer" stops
   * researching backend interviews. Their own typing always wins. */
  function pickMode(m: Mode) {
    setMode(m);
    setError(null);
    if (!roleEdited.current) setRole(m.defaultRole);
  }

  const current = session?.turns[session.turns.length - 1] ?? null;
  const awaitingAnswer = !!current && current.answer === null;
  const pacing = session?.pacing ?? null;

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
    if (!resume.trim()) {
      setError("Add your résumé first - the interview is built around it.");
      return;
    }
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
    setPending({ text, skipped });
    try {
      const state = await submitAnswer(skipped ? "" : text, skipped);
      setSession(state);
      setAnswer("");
      setPending(null);
      if (state.finished) await finish();
    } catch (err) {
      // Put it back in the box - losing a long typed answer to a blip is
      // not something they should have to retype from memory.
      setPending(null);
      setError(err instanceof Error ? err.message : "could not submit that answer");
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
      setError(err instanceof Error ? err.message : "could not build the report");
    } finally {
      setBusy(false);
      setFinishing(false);
    }
  }

  function restart() {
    roleEdited.current = false;
    stopMic();
    resetSession().catch(() => {});
    setFinishing(false);
    setPending(null);
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
    const resumeRound = mode?.key === RESUME_MODE;
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <h1>Cerebrum</h1>
          {system && (
            <p className={styles.meta}>
              asks <strong>{system.model}</strong> · judges{" "}
              <strong>{system.scorerModel}</strong> · turns driven by{" "}
              <strong>{system.coordinator === "agent" ? "main agent" : "code"}</strong>{" "}
              · {system.minQuestions}&ndash;{system.maxQuestions} questions ·{" "}
              {system.fresher ? "fresher calibration" : "experienced calibration"}
            </p>
          )}
        </header>

        {bridgeError && <p className={styles.error}>{bridgeError}</p>}
        {error && <p className={styles.error}>{error}</p>}

        <section>
          <h2 className={styles.sectionTitle}>
            <span className={styles.stepMark}>1</span> Choose the round
          </h2>
          <div className={styles.modeGrid}>
            {system?.modes.map((m) => (
              <button
                key={m.key}
                className={`${styles.modeCard} ${
                  mode?.key === m.key ? styles.modeCardActive : ""
                }`}
                onClick={() => pickMode(m)}
                disabled={busy}
                aria-pressed={mode?.key === m.key}
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

        {/* Step 2 stays out of the way until a round is picked. Showing the
            whole form up front is what made choosing a round feel like it
            did nothing and the questions below feel like a re-ask. */}
        {!mode && !bridgeError && (
          <p className={styles.stepWaiting}>
            Pick a round above and the rest of the setup appears here.
          </p>
        )}

        {mode && busy && (
          <section>
            <h2 className={styles.sectionTitle}>Setting up</h2>
            <StartingUp
              steps={
                resumeRound
                  ? [
                      "Digesting your résumé",
                      "Working out what your own projects make it fair to examine",
                      "Writing the opening question",
                    ]
                  : [
                      "Digesting your résumé",
                      `Researching what ${role || "this role"} interviews actually ask a ${level.toLowerCase() || "candidate"}`,
                      "Writing the opening question",
                    ]
              }
              note="Usually fifteen to thirty seconds. It only happens once - every question after this one comes back much faster."
            />
          </section>
        )}

        {mode && !busy && (
          <section className={styles.form}>
            <h2 className={styles.sectionTitle}>
              <span className={styles.stepMark}>2</span> About you
            </h2>
            <p className={styles.chosen}>
              <strong>{mode.name}</strong> &mdash; {mode.blurb}
            </p>

            <div className={styles.row}>
              <label className={styles.field}>
                Target role {resumeRound && <em className={styles.optional}>optional</em>}
                <input
                  value={role}
                  placeholder={resumeRound ? "e.g. Backend Engineer" : ""}
                  onChange={(e) => {
                    roleEdited.current = true;
                    setRole(e.target.value);
                  }}
                />
                <span className={styles.hint}>
                  {resumeRound
                    ? "This round runs on your own projects, so nothing is searched. It only calibrates how hard the questions are."
                    : "Filled in from the round you picked - change it if you are aiming somewhere more specific. What this role's interviews actually cover gets looked up before you start."}
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
                Paste it, or drop in a PDF. Required - the interview is built
                around it, digested before the first question.
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
              disabled={parsing}
              onChange={(e) => handleResumeFile(e.target.files?.[0])}
            />
            {parsing && (
              <p className={styles.hint}>
                <Dots label="Reading the PDF" />
              </p>
            )}

            <button
              className={styles.primary}
              onClick={handleStart}
              disabled={!resume.trim() || parsing || !!bridgeError}
            >
              Start interview
            </button>
            {!resume.trim() && (
              <span className={styles.hint}>
                Add your résumé to start.
              </span>
            )}
          </section>
        )}

        {system && (
          <section>
            <h2 className={styles.sectionTitle}>How this interview runs</h2>
            <Pipeline system={system} modeKey={mode?.key ?? ""} />
          </section>
        )}
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
              {session.mode.key === RESUME_MODE
                ? "A competency map couldn't be built from the résumé for this session - this scorecard is based on the transcript alone."
                : "Research wasn't available for this session - this scorecard is based on the model's own knowledge of the role, not a live search."}
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

        {system && (
          <section>
            <h2 className={styles.sectionTitle}>How this was judged</h2>
            <ul className={styles.guardrails}>
              <li>
                <strong>Every answer was judged on its own, as you went.</strong>{" "}
                Each one went to <code>{system.scorerModel}</code> in the
                background while you were already reading the next question -
                so it got real attention rather than a skim during one pass at
                the end. This scorecard is written from those judgements plus
                the full transcript.
              </li>
              <li>
                <strong>Nothing above was visible during the interview.</strong>{" "}
                The interviewer formed a view every turn and never showed it:
                the agent that judged and the agent that spoke were separate
                calls, and only the second one was allowed to produce words you
                saw.
              </li>
              {system.doubleCheckWrong && (
                <li>
                  <strong>Wrong answers were double-checked.</strong> Any answer
                  the fast read called incorrect got a second, focused opinion
                  on <code>{system.scorerModel}</code> before it counted against
                  you - a vague-but-right answer isn&apos;t a wrong one.
                </li>
              )}
              <li>
                <strong>Graded against a fresher bar, not a senior one.</strong>{" "}
                The question is whether a company would hire you at this level -
                naming a concept, a worked example, and reasoning about one
                trade-off out loud is a solid answer. An honest &quot;I don&apos;t
                know&quot; costs far less than a confident wrong claim.
              </li>
              <li>
                <strong>Nothing was scored on speed.</strong> There was no clock;
                how long you took to answer is not an input to any of this.
              </li>
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

  // Ending the interview waits on every background judgement still in
  // flight plus the scorecard write - easily fifteen seconds, and the
  // transcript behind it is no longer the thing to look at.
  if (finishing) {
    return (
      <div className={styles.page}>
        <header className={styles.header}>
          <h1>Writing your report</h1>
          <p className={styles.meta}>
            {session.mode.name} · {session.turns.length} question
            {session.turns.length === 1 ? "" : "s"}
          </p>
        </header>
        <BuildingReport />
      </div>
    );
  }

  const micLive = micStatus === "listening" || micStatus === "connecting";

  return (
    <div className={styles.interview}>
      <aside className={styles.sidebar}>
        <h2 className={styles.sidebarTitle}>{session.mode.name}</h2>

        {pacing && (
          <div className={styles.pacingBlock}>
            <span className={styles.pacingCount}>
              {pacing.closing ? "Wrapping up" : `Question ${pacing.questionsAsked}`}
            </span>
            <span className={styles.pacingHint}>of up to {pacing.maxQuestions}</span>
          </div>
        )}

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

        {system && (
          <PipelineCompact
            system={system}
            modeKey={session.mode.key}
            brief={session.researchBrief}
          />
        )}

        <span className={styles.spacer} />
        <button className={styles.ghost} onClick={finish} disabled={busy}>
          End interview
        </button>
        <button className={styles.ghost} onClick={restart} disabled={busy}>
          Reset
        </button>
      </aside>

      <main className={styles.main}>
        {error && <p className={styles.error}>{error}</p>}

        {session.turns.map((t, i) => {
          const last = i === session.turns.length - 1;
          // Show what they submitted straight away, before the server has
          // echoed it back onto the turn.
          const shown =
            t.answer !== null
              ? { text: t.answer, skipped: t.skipped }
              : last && pending
                ? pending
                : null;
          return (
            <article key={i} className={styles.turn}>
              <p className={styles.question}>{t.question}</p>
              {shown && (
                <p className={styles.answerText}>
                  {shown.skipped ? <em>skipped</em> : shown.text}
                </p>
              )}
            </article>
          );
        })}

        {awaitingAnswer && !busy && (
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

        {busy && !finishing && <ThinkingTurn />}
      </main>
    </div>
  );
}
