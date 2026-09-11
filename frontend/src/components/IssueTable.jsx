import { Fragment, useMemo, useState } from "react";
import { labelColor } from "../labels";

function LabelBadge({ label, errorType }) {
  if (errorType && errorType !== "none") {
    return <span style={{ color: "var(--status-critical)", fontSize: 12 }}>error: {errorType}</span>;
  }
  if (!label) return <span className="muted">—</span>;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 8, height: 8, borderRadius: 2, background: labelColor(label), flexShrink: 0 }} />
      {label}
    </span>
  );
}

export default function IssueTable({ rows, modelALabel, modelBLabel, scored, disagreementsOnlyDefault = false }) {
  const [disagreementsOnly, setDisagreementsOnly] = useState(disagreementsOnlyDefault);
  const [expanded, setExpanded] = useState(null);

  const filtered = useMemo(
    () => (disagreementsOnly ? rows.filter((r) => !r.models_agree) : rows),
    [rows, disagreementsOnly]
  );

  return (
    <div className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <label style={{ fontSize: 13, display: "flex", alignItems: "center", gap: 6 }}>
          <input
            type="checkbox"
            checked={disagreementsOnly}
            onChange={(e) => setDisagreementsOnly(e.target.checked)}
          />
          Show disagreements only
        </label>
        <span className="muted" style={{ fontSize: 12 }}>{filtered.length} of {rows.length} issues</span>
      </div>
      <div style={{ overflowX: "auto", maxHeight: 480, overflowY: "auto" }}>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Title</th>
              {scored && <th>Ground truth</th>}
              <th>{modelALabel}</th>
              <th>{modelBLabel}</th>
              <th>Agree?</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((row) => (
              <Fragment key={row.number}>
                <tr>
                  <td className="tabular-nums muted">{row.number}</td>
                  <td style={{ maxWidth: 320 }}>
                    <a href={row.html_url} target="_blank" rel="noreferrer">{row.title}</a>
                  </td>
                  {scored && <td><LabelBadge label={row.ground_truth_label} /></td>}
                  <td><LabelBadge label={row.model_a_label} errorType={row.model_a_error_type} /></td>
                  <td><LabelBadge label={row.model_b_label} errorType={row.model_b_error_type} /></td>
                  <td>
                    {row.models_agree
                      ? <span style={{ color: "var(--status-good)" }}>agree</span>
                      : <span style={{ color: "var(--status-warning)" }}>disagree</span>}
                  </td>
                  <td>
                    <button onClick={() => setExpanded(expanded === row.number ? null : row.number)}>
                      {expanded === row.number ? "hide" : "raw"}
                    </button>
                  </td>
                </tr>
                {expanded === row.number && (
                  <tr>
                    <td></td>
                    <td colSpan={scored ? 5 : 4}>
                      <div style={{ display: "flex", gap: 16, fontSize: 12, fontFamily: "monospace" }}>
                        <div style={{ flex: 1 }}>
                          <div className="muted">{modelALabel} raw output</div>
                          <pre style={{ whiteSpace: "pre-wrap" }}>{row.model_a_raw_output || "(no output)"}</pre>
                        </div>
                        <div style={{ flex: 1 }}>
                          <div className="muted">{modelBLabel} raw output</div>
                          <pre style={{ whiteSpace: "pre-wrap" }}>{row.model_b_raw_output || "(no output)"}</pre>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
