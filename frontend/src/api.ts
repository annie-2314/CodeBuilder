export type ModelOption = {
  id: string;
  label: string;
};

export type JobRecord = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  prompt: string;
  model: string;
  created_at: string;
  updated_at: string;
  project_name?: string | null;
  project_dir?: string | null;
  files: string[];
  zip_available: boolean;
  plan?: {
    name?: string;
    description?: string;
    techstack?: string;
    features?: string[];
    files?: { path: string; purpose: string }[];
  } | null;
  task_plan?: unknown;
  events: { stage: string; message?: string; filepath?: string; at?: string }[];
  error?: string | null;
};

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}

export function fetchModels() {
  return request<{ default: string; models: ModelOption[] }>("/api/models");
}

export function startGeneration(prompt: string, model: string) {
  return request<JobRecord>("/api/generate", {
    method: "POST",
    body: JSON.stringify({ prompt, model }),
  });
}

export function fetchJob(jobId: string) {
  return request<JobRecord>(`/api/jobs/${jobId}`);
}

export function downloadUrl(projectName: string) {
  return `${API_BASE}/api/projects/${encodeURIComponent(projectName)}/download`;
}

export function livePreviewUrl(projectName: string, entry = "index.html") {
  const path = entry
    .split("/")
    .map(encodeURIComponent)
    .join("/");
  return `${API_BASE}/api/projects/${encodeURIComponent(projectName)}/live/${path}`;
}

export function findHtmlEntry(files: string[]): string | null {
  const preferred = ["index.html", "index.htm", "app.html", "main.html"];
  for (const name of preferred) {
    if (files.includes(name)) return name;
  }
  const htmlFiles = files
    .filter((f) => /\.html?$/i.test(f))
    .sort((a, b) => a.split("/").length - b.split("/").length || a.length - b.length);
  return htmlFiles[0] ?? null;
}

export function fileUrl(projectName: string, filePath: string) {
  return `${API_BASE}/api/projects/${encodeURIComponent(projectName)}/files/${filePath
    .split("/")
    .map(encodeURIComponent)
    .join("/")}`;
}

export async function fetchFileContent(projectName: string, filePath: string) {
  return request<{ path: string; content: string }>(
    `/api/projects/${encodeURIComponent(projectName)}/files/${filePath
      .split("/")
      .map(encodeURIComponent)
      .join("/")}`
  );
}
