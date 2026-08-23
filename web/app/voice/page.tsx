"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./page.module.css";
import { SystemInfo, getHealth } from "@/lib/api";
import { TranscriptSpeaker, VoiceSession, VoiceStatus } from "@/lib/webrtc";

type Turn = { speaker: TranscriptSpeaker; text: string };

export default function VoiceInterview() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [role, setRole] = useState("");
  const [mode, setMode] = useState("");
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);

  const audioRef = useRef<HTMLAudioElement>(null);
  const sessionRef = useRef<VoiceSession | null>(null);

  useEffect(() => {
    getHealth()
      .then((data) => {
        setSystem(data.system);
        setRole(data.system.roles[0] ?? "");
        setMode(data.system.modes[0] ?? "");
      })
      .catch(() => setError("Bridge not reachable. Is the backend running?"));

    // Stop any live mic/connection if the user navigates away mid-interview.
    return () => sessionRef.current?.stop();
  }, []);

  function handleStart() {
    if (!audioRef.current) return;
    setError(null);
    setTurns([]);

    const session = new VoiceSession(audioRef.current, {
      onStatusChange: setStatus,
      onError: setError,
      onTranscript: (speaker, text) => setTurns((t) => [...t, { speaker, text }]),
    });
    sessionRef.current = session;
    session.start(role, mode);
  }

  function handleEnd() {
    sessionRef.current?.stop();
    sessionRef.current = null;
  }

  const live = status === "connecting" || status === "connected";

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>Interview - voice</h1>

        {error && <p className={styles.error}>{error}</p>}

        {!live && (
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
            <button onClick={handleStart} disabled={!role || !mode}>
              Start interview
            </button>
          </section>
        )}

        {live && (
          <section className={styles.session}>
            <p className={styles.status}>
              Status: <strong>{status}</strong>
            </p>
            <button onClick={handleEnd}>End interview</button>

            <div className={styles.transcript}>
              {turns.map((t, i) => (
                <p
                  key={i}
                  className={t.speaker === "you" ? styles.you : styles.interviewer}
                >
                  <strong>{t.speaker === "you" ? "You" : "Interviewer"}:</strong>{" "}
                  {t.text}
                </p>
              ))}
              {turns.length === 0 && (
                <p className={styles.note}>Waiting for the interviewer to speak...</p>
              )}
            </div>
          </section>
        )}

        {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
        <audio ref={audioRef} autoPlay />
      </main>
    </div>
  );
}
