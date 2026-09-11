const BASE = import.meta.env.VITE_API_BASE || "/api";

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export const api = {
  health: () => get("/health"),
  models: () => get("/models"),
  corpus: () => get("/corpus"),
  runs: () => get("/runs"),
  run: (runId) => get(`/runs/${runId}`),
  startJob: (req) => post("/jobs", req),
  job: (jobId) => get(`/jobs/${jobId}`),
};
