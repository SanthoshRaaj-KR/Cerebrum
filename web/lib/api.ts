// Set by docker compose; falls back to the local default so running the
// console with `npm run dev` outside Docker needs no configuration.
export const BRIDGE_URL =
  process.env.NEXT_PUBLIC_BRIDGE_URL || "http://127.0.0.1:7332";

export type Mode = {
  key: string;
  name: string;
  blurb: string;
  /** Shown on the setup card as a preview of what this mode is about - not
   * a live rubric any more. Nothing is scored until the report. */
  dims: string[];
};

export type SystemInfo = {
  model: string;
  fresher: boolean;
  durationMinutes: number;
  modes: Mode[];
};

export type Turn = {
  question: string;
  answer: string | null;
  skipped: boolean;
};

export type Clock = {
  startedAt: number;
  durationSeconds: number;
  elapsedSeconds: number;
  remainingSeconds: number;
  phase: "opening" | "core" | "depth" | "closing";
  expired: boolean;
};

export type ResearchBrief = {
  grounded: boolean;
  competencies: string[];
  realQuestions: string[];
  sources: string[];
};

export type SessionState = {
  mode: { key: string; name: string };
  role: string;
  level: string;
  finished: boolean;
  clock: Clock | null;
  turns: Turn[];
  researchBrief: ResearchBrief | null;
};

export type CompetencyResult = {
  name: string;
  status: "solid" | "developing" | "not_shown" | "not_covered";
  evidence: string;
};

export type Scorecard = {
  verdict: "strong_yes" | "yes" | "borderline" | "not_yet";
  score: number;
  headline: string;
  strengths: string[];
  gaps: string[];
  notes: string[];
  competencies: CompetencyResult[];
  sources: string[];
  grounded: boolean;
};

export type SessionReport = SessionState & { scorecard: Scorecard };

async function asJson<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(
      (body as { detail?: string }).detail || `request failed (${res.status})`
    );
  }
  return body as T;
}

export async function getHealth(): Promise<{ ok: boolean; system: SystemInfo }> {
  return asJson(await fetch(`${BRIDGE_URL}/api/health`));
}

/** PDF in, plain text out. The interview works from whatever text ends up
 * in the résumé box, so this is a convenience rather than a required step. */
export async function extractResume(file: File): Promise<{ text: string }> {
  const form = new FormData();
  form.append("file", file);
  return asJson(
    await fetch(`${BRIDGE_URL}/api/resume/extract`, { method: "POST", body: form })
  );
}

export async function startSession(body: {
  mode: string;
  role: string;
  level: string;
  resume: string;
  /** Overrides interview.duration_minutes for this session. The console
   * never sends this - it's for the quality-check harness. */
  minutes?: number;
}): Promise<SessionState> {
  return asJson(
    await fetch(`${BRIDGE_URL}/api/session/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

export async function submitAnswer(
  text: string,
  skipped = false
): Promise<SessionState> {
  return asJson(
    await fetch(`${BRIDGE_URL}/api/session/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, skipped }),
    })
  );
}

export async function getSession(): Promise<{ session: SessionState | null }> {
  return asJson(await fetch(`${BRIDGE_URL}/api/session`));
}

/** Ends the interview and returns the state plus the scorecard - the first
 * and only point anything evaluative reaches the candidate. */
export async function getReport(): Promise<SessionReport> {
  return asJson(
    await fetch(`${BRIDGE_URL}/api/session/report`, { method: "POST" })
  );
}

export async function resetSession(): Promise<{ ok: boolean }> {
  return asJson(
    await fetch(`${BRIDGE_URL}/api/session/reset`, { method: "POST" })
  );
}
