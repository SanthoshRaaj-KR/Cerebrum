// Set by docker compose; falls back to the local default so running the
// console with `npm run dev` outside Docker needs no configuration.
export const BRIDGE_URL =
  process.env.NEXT_PUBLIC_BRIDGE_URL || "http://127.0.0.1:7332";

export type Mode = {
  key: string;
  name: string;
  blurb: string;
  /** The three rubric dimensions every answer in this mode is scored on. */
  dims: string[];
  count: number;
};

export type SystemInfo = {
  model: string;
  fresher: boolean;
  questionsPerSession: number;
  modes: Mode[];
};

export type DimScore = { name: string; score: number };

export type Grade = {
  score: number;
  verdict: string;
  strength: string;
  gap: string;
  /** What the question was actually about - the interviewer deviates from
   * the plan, so this is the honest sidebar label. */
  topic: string;
  rubric: DimScore[];
};

export type Turn = {
  index: number;
  short: string;
  question: string;
  hint: string;
  answer: string | null;
  skipped: boolean;
  grade: Grade | null;
};

export type PlanSlot = { num: number; short: string; score: number | null };

export type SessionState = {
  mode: { key: string; name: string; dims: string[] };
  role: string;
  level: string;
  index: number;
  total: number;
  finished: boolean;
  plan: PlanSlot[];
  turns: Turn[];
  average: number | null;
  dimensionAverages: { name: string; score: number | null }[];
};

export type Report = { headline: string; notes: string[] };

export type SessionReport = SessionState & { report: Report };

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

/** Ends the interview and returns the state plus the coach's notes. */
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
