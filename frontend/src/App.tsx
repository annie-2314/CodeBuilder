import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  downloadUrl,
  fetchFileContent,
  fetchJob,
  fetchModels,
  findHtmlEntry,
  JobRecord,
  livePreviewUrl,
  ModelOption,
  startGeneration,
} from "./api";
import "./App.css";

const EXAMPLES = [
  "Build a calculator web app with add, subtract, multiply and divide buttons.",
  "Create a to-do list application using HTML, CSS, and JavaScript.",
  "Create a simple blog API in FastAPI with a SQLite database.",
];

type ResultTab = "live" | "code";

export default function App() {
  const [models, setModels] = useState<ModelOption[]>([]);
  const [model, setModel] = useState("openai/gpt-oss-120b");
  const [prompt, setPrompt] = useState(EXAMPLES[0]);
  const [job, setJob] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string>("");
  const [resultTab, setResultTab] = useState<ResultTab>("live");
  const [iframeKey, setIframeKey] = useState(0);

  useEffect(() => {
    fetchModels()
      .then((data) => {
        setModels(data.models);
        setModel(data.default || data.models[0]?.id);
      })
      .catch((err: Error) => {
        setError(
          err.message ||
            "Cannot reach API. Start the backend with: uvicorn api.server:app --reload"
        );
      });
  }, []);

  useEffect(() => {
    if (!job || (job.status !== "queued" && job.status !== "running")) {
      return;
    }
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchJob(job.job_id);
        setJob(next);
        if (next.status === "completed" || next.status === "failed") {
          setBusy(false);
        }
      } catch (err) {
        setBusy(false);
        setError(err instanceof Error ? err.message : "Failed to poll job");
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job]);

  useEffect(() => {
    if (job?.status === "completed" && job.files.length > 0) {
      setPreviewPath(job.files[0]);
      const entry = findHtmlEntry(job.files);
      setResultTab(entry ? "live" : "code");
      setIframeKey((k) => k + 1);
    }
  }, [job?.status, job?.files]);

  useEffect(() => {
    if (!job?.project_name || !previewPath) {
      setPreviewContent("");
      return;
    }
    fetchFileContent(job.project_name, previewPath)
      .then((data) => setPreviewContent(data.content))
      .catch(() => setPreviewContent("// Unable to load file"));
  }, [job?.project_name, previewPath]);

  const latestMessage = useMemo(() => {
    if (!job?.events?.length) return "Waiting for agents...";
    const last = job.events[job.events.length - 1];
    return last.message || last.stage;
  }, [job]);

  const htmlEntry = useMemo(
    () => (job?.files ? findHtmlEntry(job.files) : null),
    [job?.files]
  );

  const liveUrl =
    job?.project_name && htmlEntry
      ? livePreviewUrl(job.project_name, htmlEntry)
      : null;

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setJob(null);
    setPreviewPath(null);
    setBusy(true);
    try {
      const created = await startGeneration(prompt.trim(), model);
      setJob(created);
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : "Generation failed");
    }
  }

  return (
    <div className="shell">
      <header className="hero">
        <p className="brand">Code Buddy</p>
        <h1>Describe an app. Get a working project.</h1>
        <p className="lede">
          Planner, Architect, and Coder agents turn your prompt into multi-file code —
          preview it live, then download the zip.
        </p>
      </header>

      <main className="layout">
        <section className="compose">
          <form onSubmit={onSubmit}>
            <label className="field">
              <span>Project prompt</span>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={5}
                required
                minLength={3}
                disabled={busy}
              />
            </label>

            <div className="row">
              <label className="field grow">
                <span>Model</span>
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  disabled={busy || models.length === 0}
                >
                  {(models.length ? models : [{ id: model, label: model }]).map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </select>
              </label>
              <button className="cta" type="submit" disabled={busy || prompt.trim().length < 3}>
                {busy ? "Generating…" : "Generate project"}
              </button>
            </div>

            <div className="examples">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  type="button"
                  className="chip"
                  disabled={busy}
                  onClick={() => setPrompt(example)}
                >
                  {example}
                </button>
              ))}
            </div>
          </form>

          {error && <p className="error">{error}</p>}

          {job && (
            <div className="status-panel" data-status={job.status}>
              <div className="status-head">
                <span className="status-pill">{job.status}</span>
                <span className="status-msg">{latestMessage}</span>
              </div>
              {busy && <div className="progress-bar" aria-hidden />}
              <ol className="event-list">
                {job.events.slice(-8).map((event, index) => (
                  <li key={`${event.stage}-${index}`}>
                    <code>{event.stage}</code> {event.message || event.filepath || ""}
                  </li>
                ))}
              </ol>
              {job.error && <p className="error">{job.error}</p>}
            </div>
          )}
        </section>

        <section className="result">
          {!job || job.status !== "completed" ? (
            <div className="empty">
              <h2>Pipeline</h2>
              <p>planner → architect → coder (loops until every file is written)</p>
              <div className="flow">
                <span>planner</span>
                <span>architect</span>
                <span>coder</span>
              </div>
            </div>
          ) : (
            <>
              <div className="result-head">
                <div>
                  <h2>{job.plan?.name || job.project_name}</h2>
                  <p>{job.plan?.description}</p>
                  <p className="meta">
                    {job.plan?.techstack} · {job.files.length} files · {job.model}
                  </p>
                </div>
                <div className="result-actions">
                  {liveUrl && (
                    <a className="download secondary" href={liveUrl} target="_blank" rel="noreferrer">
                      Open live tab
                    </a>
                  )}
                  {job.project_name && (
                    <a className="download" href={downloadUrl(job.project_name)}>
                      Download ZIP
                    </a>
                  )}
                </div>
              </div>

              {job.plan?.features && (
                <ul className="features">
                  {job.plan.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>
              )}

              <div className="tabs" role="tablist">
                <button
                  type="button"
                  role="tab"
                  className={resultTab === "live" ? "active" : ""}
                  aria-selected={resultTab === "live"}
                  onClick={() => setResultTab("live")}
                  disabled={!htmlEntry}
                >
                  Live preview
                </button>
                <button
                  type="button"
                  role="tab"
                  className={resultTab === "code" ? "active" : ""}
                  aria-selected={resultTab === "code"}
                  onClick={() => setResultTab("code")}
                >
                  Code
                </button>
              </div>

              {resultTab === "live" ? (
                <div className="live-panel">
                  {liveUrl ? (
                    <>
                      <div className="live-toolbar">
                        <span>Interactive preview — click buttons inside the frame to test</span>
                        <button type="button" className="chip refresh" onClick={() => setIframeKey((k) => k + 1)}>
                          Refresh
                        </button>
                      </div>
                      <iframe
                        key={iframeKey}
                        className="live-frame"
                        title="Live project preview"
                        src={liveUrl}
                        sandbox="allow-scripts allow-forms allow-same-origin allow-modals"
                      />
                    </>
                  ) : (
                    <p className="muted-note">
                      No HTML entry file found. Switch to <strong>Code</strong> or run API
                      projects locally from the project folder.
                    </p>
                  )}
                </div>
              ) : (
                <div className="files-grid">
                  <div className="file-list">
                    <h3>Files</h3>
                    {job.files.map((file) => (
                      <button
                        key={file}
                        type="button"
                        className={file === previewPath ? "active" : ""}
                        onClick={() => setPreviewPath(file)}
                      >
                        {file}
                      </button>
                    ))}
                  </div>
                  <pre className="preview">
                    <code>{previewContent}</code>
                  </pre>
                </div>
              )}

              {job.project_dir && (
                <p className="local-path">
                  Local path: <code>{job.project_dir}</code>
                </p>
              )}
            </>
          )}
        </section>
      </main>
    </div>
  );
}
