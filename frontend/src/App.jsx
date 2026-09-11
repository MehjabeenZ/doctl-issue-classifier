import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import RunControls from "./components/RunControls";
import ScoredView from "./components/ScoredView";
import UnscoredView from "./components/UnscoredView";
import OperationalMetrics from "./components/OperationalMetrics";

const TABS = ["Scored", "Unscored", "Operational"];

export default function App() {
  const [models, setModels] = useState([]);
  const [corpus, setCorpus] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [tab, setTab] = useState("Scored");
  const pollRef = useRef(null);

  useEffect(() => {
    api.models().then((d) => setModels(d.models)).catch((e) => setError(String(e)));
    api.corpus().then(setCorpus).catch((e) => setError(String(e)));
    return () => clearInterval(pollRef.current);
  }, []);

  const handleRun = async (request) => {
    setError(null);
    setRunning(true);
    try {
      const { job_id } = await api.startJob(request);
      pollRef.current = setInterval(async () => {
        const job = await api.job(job_id);
        if (job.status === "done") {
          clearInterval(pollRef.current);
          const runResult = await api.run(job.run_id);
          setResult(runResult);
          setRunning(false);
        } else if (job.status === "error") {
          clearInterval(pollRef.current);
          setError(job.error);
          setRunning(false);
        }
      }, 1200);
    } catch (e) {
      setError(String(e));
      setRunning(false);
    }
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: 24, display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h1 style={{ fontSize: 22, marginBottom: 4 }}>doctl issue-classification eval harness</h1>
        <div className="muted" style={{ fontSize: 13 }}>
          Compare two DigitalOcean Serverless Inference models on the doctl GitHub issue corpus.
        </div>
      </div>

      <RunControls models={models} corpus={corpus} onRun={handleRun} running={running} defaultConcurrency={8} />

      {error && (
        <div className="card" style={{ borderColor: "var(--status-critical)", color: "var(--status-critical)" }}>
          {error}
        </div>
      )}

      {result ? (
        <>
          <div style={{ display: "flex", gap: 8, borderBottom: "1px solid var(--gridline)" }}>
            {TABS.map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                style={{
                  background: "none", border: "none", padding: "8px 4px", cursor: "pointer",
                  borderBottom: tab === t ? "2px solid var(--label-bug)" : "2px solid transparent",
                  fontWeight: tab === t ? 600 : 400, color: "var(--text-primary)",
                }}
              >
                {t}
              </button>
            ))}
          </div>
          {tab === "Scored" && <ScoredView result={result} />}
          {tab === "Unscored" && <UnscoredView result={result} />}
          {tab === "Operational" && <OperationalMetrics result={result} />}
        </>
      ) : (
        <div className="muted">Run a comparison to see results.</div>
      )}
    </div>
  );
}
