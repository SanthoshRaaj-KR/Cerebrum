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
  /** The target role this round implies, used to prefill the setup form.
   * Comes from the mode module, so the console never has to guess - empty
   * for the résumé round, which has no role to search for. */
  defaultRole: string;
};

/** The real configuration, read off /api/health rather than hardcoded in
 * the console. Everything the "how this works" panel shows comes from
 * here, so what the screen claims and what the backend does cannot drift
 * apart. */
export type SystemInfo = {
  /** Asks the questions and, in agent mode, drives the turn. */
  model: string;
  /** Judges: the background per-answer score and the wrong-claim recheck. */
  scorerModel: string;
  /** Who decides the next move - the LLM main agent, or the deterministic
   * ladder. Both enforce the same invariants in code. */
  coordinator: "code" | "agent";
  /** Whether a `wrong` read gets a second opinion before it counts. */
  doubleCheckWrong: boolean;
  fresher: boolean;
  minQuestions: number;
  maxQuestions: number;
  researchEnabled: boolean;
  /** Search providers in fallback order, e.g. ["tavily", "brave"]. */
  researchProviders: string[];
  /** Whether a finished interview can be kept. False is a normal state -
   * it just means no MONGODB_URI in .env - so the console explains it
   * rather than hiding the feature or letting the button fail. */
  storageEnabled: boolean;
  modes: Mode[];
};

export type Turn = {
  question: string;
  answer: string | null;
  skipped: boolean;
};

/** Replaces the old clock. There's no timer any more - the interview runs
 * on coverage of the role's competencies, so all the UI shows is where it
 * is in that: how many questions in, the ceiling, and whether it's
 * wrapping up. Nothing here is evaluative. */
export type Pacing = {
  questionsAsked: number;
  /** The hard ceiling. Rarely what the interview actually runs to. */
  maxQuestions: number;
  /** What it is expected to run to - one question per competency plus room
   * for follow-ups. An estimate, not a schedule: the interview really ends
   * when every competency has a read. The progress bar fills against this
   * and the copy is careful never to call it a deadline. */
  plannedQuestions: number;
  estimatedMinutes: number;
  competencyCount: number;
  closing: boolean;
};

export type ResearchBrief = {
  grounded: boolean;
  /** Where the competency map came from: a live role search, or the
   * candidate's own résumé via the gateway agent (résumé mode has no
   * external syllabus to search). */
  source: "research" | "resume";
  competencies: string[];
  sources: string[];
};

export type SessionState = {
  mode: { key: string; name: string };
  role: string;
  level: string;
  finished: boolean;
  pacing: Pacing;
  turns: Turn[];
  researchBrief: ResearchBrief | null;
};

export type CompetencyResult = {
  name: string;
  status: "solid" | "developing" | "not_shown" | "not_covered";
  evidence: string;
};

/** The background scorer's read on one answer. This is what makes the
 * report detailed rather than a grade: `gap` says what was missing,
 * `better` says what a strong answer to that exact question sounds like,
 * and `improve` is the one thing to do differently next time. */
export type AnswerVerdict = {
  index: number;
  question: string;
  competency: string;
  correct: boolean;
  depth: "solid" | "partial" | "absent";
  /** What they actually demonstrated. Empty unless the answer was correct. */
  evidence: string;
  gap: string;
  better: string;
  improve: string;
  answer: string;
  skipped: boolean;
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
  /** Per question, in the order they were asked - the working the summary
   * above was written from. */
  answers: AnswerVerdict[];
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
  /** Only the résumé round sends one - it is that round's whole syllabus.
   * The other five are subject rounds and never needed a CV. */
  resume?: string;
  /** Overrides interview.max_questions for this session. The console never
   * sends this - it's for the quality-check harness, to keep runs short. */
  maxQuestions?: number;
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

/* -- saved interviews -------------------------------------------------------
 *
 * The one part of this product that outlives the bridge process. Saving is
 * explicit and only ever happens on a finished interview - see store.py.
 */

/** What the library grid needs: a card's worth, not the transcript. */
export type SavedSummary = {
  id: string;
  savedAt: string;
  mode: { key: string; name: string };
  role: string;
  verdict: Scorecard["verdict"];
  score: number;
  headline: string;
  questionCount: number;
};

/** A saved interview in full. Deliberately close to `Scorecard` plus the
 * session context, so ReportScreen can render a live report and a saved
 * one from the same props and the two cannot drift apart. */
export type SavedInterview = SavedSummary & {
  startedAt: string | null;
  level: string;
  strengths: string[];
  gaps: string[];
  notes: string[];
  competencies: CompetencyResult[];
  answers: AnswerVerdict[];
  turns: Turn[];
  sources: string[];
  grounded: boolean;
  researchSource: "research" | "resume" | null;
  resume: string | null;
  system: {
    model: string | null;
    scorerModel: string | null;
    coordinator: string | null;
    fresher: boolean | null;
  };
};

export type ProgressStats = {
  count: number;
  average?: number;
  best?: number;
  /** Oldest first - a trend line that runs backwards is a trap. */
  trend: { at: string; score: number; mode: string; id: string }[];
  byMode: { key: string; name: string; count: number; average: number }[];
  /** Competencies that came back as developing or not-shown, most
   * frequent first. `not_covered` is excluded: never reaching an area is
   * not the same as being weak at it. */
  recurringGaps: { name: string; times: number }[];
};

/** Stores the interview currently in the bridge. Only valid once the
 * report has been generated. */
export async function saveInterview(): Promise<{ id: string }> {
  return asJson(
    await fetch(`${BRIDGE_URL}/api/interviews`, { method: "POST" })
  );
}

export async function listInterviews(
  mode?: string
): Promise<{ interviews: SavedSummary[] }> {
  const q = mode ? `?mode=${encodeURIComponent(mode)}` : "";
  return asJson(await fetch(`${BRIDGE_URL}/api/interviews${q}`));
}

export async function getInterview(id: string): Promise<SavedInterview> {
  return asJson(await fetch(`${BRIDGE_URL}/api/interviews/${id}`));
}

export async function deleteInterview(id: string): Promise<{ ok: boolean }> {
  return asJson(
    await fetch(`${BRIDGE_URL}/api/interviews/${id}`, { method: "DELETE" })
  );
}

export async function getProgress(): Promise<ProgressStats> {
  return asJson(await fetch(`${BRIDGE_URL}/api/interviews/stats`));
}
