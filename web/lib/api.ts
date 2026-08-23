const BRIDGE_URL = "http://127.0.0.1:7332";

export type Project = {
  name: string;
  description: string;
  tech: string[];
};

export type CandidateProfile = {
  name: string;
  education: string[];
  skills: string[];
  projects: Project[];
  experience: string[];
};

export type SystemInfo = {
  model: string;
  fresher: boolean;
  roles: string[];
  modes: string[];
};

async function asJson<T>(res: Response): Promise<T> {
  const body = await res.json();
  if (!res.ok) {
    throw new Error(body.detail || `request failed (${res.status})`);
  }
  return body as T;
}

export async function getHealth(): Promise<{ ok: boolean; system: SystemInfo }> {
  const res = await fetch(`${BRIDGE_URL}/api/health`);
  return asJson(res);
}

export async function getResume(): Promise<{ profile: CandidateProfile | null }> {
  const res = await fetch(`${BRIDGE_URL}/api/resume`);
  return asJson(res);
}

export async function uploadResume(
  file: File
): Promise<{ profile: CandidateProfile }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BRIDGE_URL}/api/resume`, {
    method: "POST",
    body: form,
  });
  return asJson(res);
}
