"use client";

import { useEffect, useState } from "react";
import styles from "./page.module.css";

const BRIDGE_URL = "http://127.0.0.1:7332";

type SystemInfo = {
  model: string;
  fresher: boolean;
  roles: string[];
  modes: string[];
};

export default function Home() {
  const [system, setSystem] = useState<SystemInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${BRIDGE_URL}/api/health`)
      .then((r) => r.json())
      .then((data) => setSystem(data.system))
      .catch(() => setError("Bridge not reachable at " + BRIDGE_URL));
  }, []);

  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>Interview Agent</h1>
        {error && <p className={styles.error}>{error}</p>}
        {system && (
          <ul className={styles.status}>
            <li>model: {system.model}</li>
            <li>fresher calibration: {String(system.fresher)}</li>
            <li>roles: {system.roles.join(", ")}</li>
            <li>modes: {system.modes.join(", ")}</li>
          </ul>
        )}
        {!system && !error && <p>Connecting to the bridge...</p>}
      </main>
    </div>
  );
}
