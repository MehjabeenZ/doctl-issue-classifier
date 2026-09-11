import { useEffect, useState } from "react";

// The two models the screening run (see DESIGN_DECISIONS.md §3) recommends
// comparing — seeded as the default selection so opening the app shows the
// actual recommendation, not whichever two models happen to load first.
const RECOMMENDED_MODEL_A = "mistral-3-14B";
const RECOMMENDED_MODEL_B = "deepseek-4-flash";

export default function RunControls({ models, corpus, onRun, running, defaultConcurrency }) {
  const [modelA, setModelA] = useState("");
  const [modelB, setModelB] = useState("");
  const [concurrency, setConcurrency] = useState(defaultConcurrency || 8);
  const [limit, setLimit] = useState("");

  // models arrives asynchronously (fetched after mount) — seed the selects once
  // it does, rather than only at the initial (empty) render.
  useEffect(() => {
    if (models.length === 0) return;
    setModelA((current) => current || (models.includes(RECOMMENDED_MODEL_A) ? RECOMMENDED_MODEL_A : models[0]));
    setModelB((current) => current || (models.includes(RECOMMENDED_MODEL_B) ? RECOMMENDED_MODEL_B : models[1] || models[0]));
  }, [models]);

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {corpus && (
        <div className="muted" style={{ fontSize: 13 }}>
          Corpus: {corpus.total_issues} issues ({corpus.scored_count} scored, {corpus.unscored_count} unscored)
        </div>
      )}
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
          Model A
          <select value={modelA} onChange={(e) => setModelA(e.target.value)}>
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
          Model B
          <select value={modelB} onChange={(e) => setModelB(e.target.value)}>
            {models.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
          Concurrency
          <input
            type="number" min={1} max={64} value={concurrency}
            onChange={(e) => setConcurrency(Number(e.target.value))}
            style={{ width: 80 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 13 }}>
          Limit (optional, for a quick smoke run)
          <input
            type="number" min={1} placeholder="full corpus" value={limit}
            onChange={(e) => setLimit(e.target.value)}
            style={{ width: 140 }}
          />
        </label>
        <button
          disabled={running || !modelA || !modelB}
          onClick={() => onRun({ model_a: modelA, model_b: modelB, concurrency, limit: limit ? Number(limit) : undefined })}
        >
          {running ? "Running…" : "Run comparison"}
        </button>
      </div>
    </div>
  );
}
