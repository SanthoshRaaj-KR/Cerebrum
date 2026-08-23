"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./page.module.css";
import {
  CandidateProfile,
  SystemInfo,
  getHealth,
  getResume,
  uploadResume,
} from "@/lib/api";

export default function Home() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [hasFile, setHasFile] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getHealth()
      .then((data) => setSystem(data.system))
      .catch(() => setBridgeError("Bridge not reachable. Is the backend running?"));
    getResume()
      .then((data) => setProfile(data.profile))
      .catch(() => {
        /* no profile yet - fine */
      });
  }, []);

  async function handleUpload() {
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const { profile } = await uploadResume(file);
      setProfile(profile);
      if (fileInput.current) fileInput.current.value = "";
      setHasFile(false);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>Interview Agent</h1>

        {bridgeError && <p className={styles.error}>{bridgeError}</p>}
        {system && (
          <ul className={styles.status}>
            <li>model: {system.model}</li>
            <li>fresher calibration: {String(system.fresher)}</li>
            <li>roles: {system.roles.join(", ")}</li>
            <li>modes: {system.modes.join(", ")}</li>
          </ul>
        )}

        <section className={styles.upload}>
          <h2>Resume</h2>
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf"
            onChange={(e) => {
              setHasFile(!!e.target.files?.length);
              setUploadError(null);
            }}
          />
          <button onClick={handleUpload} disabled={uploading || !hasFile}>
            {uploading ? "Parsing..." : "Upload resume"}
          </button>
          {uploadError && <p className={styles.error}>{uploadError}</p>}
        </section>

        {profile && (
          <section className={styles.profile}>
            <h2>{profile.name || "Parsed profile"}</h2>

            {profile.education.length > 0 && (
              <div>
                <h3>Education</h3>
                <ul>
                  {profile.education.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}

            {profile.skills.length > 0 && (
              <div>
                <h3>Skills</h3>
                <p>{profile.skills.join(", ")}</p>
              </div>
            )}

            {profile.projects.length > 0 && (
              <div>
                <h3>Projects</h3>
                <ul>
                  {profile.projects.map((p, i) => (
                    <li key={i}>
                      <strong>{p.name}</strong> - {p.description}
                      {p.tech.length > 0 && (
                        <span className={styles.tech}> ({p.tech.join(", ")})</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {profile.experience.length > 0 && (
              <div>
                <h3>Experience</h3>
                <ul>
                  {profile.experience.map((e, i) => (
                    <li key={i}>{e}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
