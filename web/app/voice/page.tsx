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
  const [muted, setMuted] = useState(false);

  const audioRef = useRef<HTMLAudioElement>(null);
  const sessionRef = useRef<VoiceSession | null>(null);
  const live = status === "connecting" || status === "connected";

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
    // status (not sessionRef) is the double-click guard: it correctly
    // resets on failure/end so a retry isn't permanently blocked, unlike
    // checking whether sessionRef still holds a (by then stopped) session.
    if (!audioRef.current || live) return;
    setError(null);
    setTurns([]);
    setMuted(false);

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

  function handleToggleMute() {
    if (!sessionRef.current) return;
    setMuted(sessionRef.current.toggleMute());
  }

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
              {status === "connected" && (
                <span className={muted ? styles.muted : styles.liveDot}>
                  {muted ? " muted" : " mic live"}
                </span>
              )}
            </p>
            <div className={styles.controls}>
              <button onClick={handleToggleMute} disabled={status !== "connected"}>
                {muted ? "Unmute" : "Mute"}
              </button>
              <button onClick={handleEnd}>End interview</button>
            </div>

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
