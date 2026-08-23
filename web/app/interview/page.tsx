"use client";

import { useEffect, useState } from "react";
import styles from "./page.module.css";
import { SystemInfo, getHealth, startSession, submitAnswer } from "@/lib/api";

type Turn = { speaker: "interviewer" | "you"; text: string };

export default function InterviewTestHarness() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [role, setRole] = useState("");
  const [mode, setMode] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [answer, setAnswer] = useState("");
  const [started, setStarted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHealth()
      .then((data) => {
        setSystem(data.system);
        setRole(data.system.roles[0] ?? "");
        setMode(data.system.modes[0] ?? "");
      })
      .catch(() => setError("Bridge not reachable. Is the backend running?"));
  }, []);

  async function handleStart() {
    setBusy(true);
    setError(null);
    try {
      const { question } = await startSession(role, mode);
      setTurns([{ speaker: "interviewer", text: question }]);
      setStarted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not start interview");
    } finally {
      setBusy(false);
    }
  }

  async function handleSend() {
    const text = answer.trim();
    if (!text) return;
    setTurns((t) => [...t, { speaker: "you", text }]);
    setAnswer("");
    setBusy(true);
    setError(null);
    try {
      const { question } = await submitAnswer(text);
      setTurns((t) => [...t, { speaker: "interviewer", text: question }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not get next question");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>Interview - text harness</h1>
        <p className={styles.note}>
          Temporary text-only view for validating interview logic before the
          voice UI lands.
        </p>

        {error && <p className={styles.error}>{error}</p>}

        {!started && (
          <section className={styles.setup}>
            <label>
              Role
              <select value={role} onChange={(e) => setRole(e.target.value)}>
                {system?.roles.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Mode
              <select value={mode} onChange={(e) => setMode(e.target.value)}>
                {system?.modes.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <button onClick={handleStart} disabled={busy || !role || !mode}>
              {busy ? "Starting..." : "Start interview"}
            </button>
          </section>
        )}

        {started && (
          <section className={styles.transcript}>
            {turns.map((t, i) => (
              <p key={i} className={t.speaker === "you" ? styles.you : styles.interviewer}>
                <strong>{t.speaker === "you" ? "You" : "Interviewer"}:</strong> {t.text}
              </p>
            ))}

            <div className={styles.composer}>
              <input
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSend();
                }}
                placeholder="Type your answer..."
                disabled={busy}
              />
              <button onClick={handleSend} disabled={busy || !answer.trim()}>
                {busy ? "..." : "Send"}
              </button>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
