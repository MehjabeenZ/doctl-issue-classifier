import { LABELS, labelColor } from "../labels";

const SEQ_STEPS = ["--seq-100", "--seq-200", "--seq-300", "--seq-400", "--seq-500", "--seq-600", "--seq-700"];

// Cells shade by row-normalized magnitude (sequential blue) — identity of the
// true/predicted class lives in the axis labels (categorical swatches), never in
// the cell's own hue, so the two encodings never fight.
function cellStyle(count, rowTotal) {
  if (rowTotal === 0) return { background: "transparent" };
  const pct = count / rowTotal;
  const stepIndex = count === 0 ? -1 : Math.min(SEQ_STEPS.length - 1, Math.floor(pct * SEQ_STEPS.length));
  if (stepIndex < 0) return { background: "transparent" };
  const dark = stepIndex >= 4;
  return {
    background: `var(${SEQ_STEPS[stepIndex]})`,
    color: dark ? "#ffffff" : "#0b0b0b",
  };
}

function AxisLabel({ label }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          width: 8, height: 8, borderRadius: 2, background: labelColor(label), flexShrink: 0,
        }}
      />
      {label}
    </span>
  );
}

export default function ConfusionMatrix({ title, matrix, supportByClass }) {
  return (
    <div className="card">
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        rows = ground truth, columns = predicted · shaded by % of row
      </div>
      <div style={{ overflowX: "auto" }}>
        <table>
          <thead>
            <tr>
              <th></th>
              {LABELS.map((l) => (
                <th key={l} style={{ textAlign: "center" }}><AxisLabel label={l} /></th>
              ))}
              <th className="muted" style={{ textAlign: "right" }}>support</th>
            </tr>
          </thead>
          <tbody>
            {LABELS.map((trueLabel) => {
              const row = matrix?.[trueLabel] || {};
              const rowTotal = LABELS.reduce((sum, l) => sum + (row[l] || 0), 0);
              const support = supportByClass?.[trueLabel] ?? rowTotal;
              return (
                <tr key={trueLabel}>
                  <th><AxisLabel label={trueLabel} /></th>
                  {LABELS.map((predLabel) => {
                    const count = row[predLabel] || 0;
                    return (
                      <td
                        key={predLabel}
                        className="tabular-nums"
                        style={{ textAlign: "center", fontWeight: trueLabel === predLabel ? 700 : 400, ...cellStyle(count, rowTotal) }}
                        title={`true=${trueLabel} pred=${predLabel}: ${count}`}
                      >
                        {support === 0 ? "—" : count}
                      </td>
                    );
                  })}
                  <td className="muted tabular-nums" style={{ textAlign: "right" }}>
                    {support === 0 ? "no data" : support}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
