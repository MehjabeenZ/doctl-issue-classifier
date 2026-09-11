import { LABELS, labelColor } from "../labels";

// Two single-series bar charts sharing one scale (the shared max), so bar length
// is comparable between models at a glance without resorting to a dual-axis chart.
export default function DistributionBars({ modelALabel, modelBLabel, distA, distB }) {
  const max = Math.max(1, ...LABELS.map((l) => Math.max(distA?.[l] || 0, distB?.[l] || 0)));

  const Chart = ({ title, dist }) => (
    <div style={{ flex: 1, minWidth: 220 }}>
      <div className="secondary" style={{ fontSize: 12, marginBottom: 8 }}>{title}</div>
      {LABELS.map((label) => {
        const count = dist?.[label] || 0;
        const pct = (count / max) * 100;
        return (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <div style={{ width: 96, fontSize: 12 }}>{label}</div>
            <div style={{ flex: 1, background: "var(--gridline)", borderRadius: 4, height: 10 }}>
              <div
                style={{
                  width: `${pct}%`,
                  height: "100%",
                  background: labelColor(label),
                  borderRadius: 4,
                  transition: "width 0.2s",
                }}
              />
            </div>
            <div className="tabular-nums muted" style={{ width: 36, textAlign: "right", fontSize: 12 }}>{count}</div>
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="card" style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
      <Chart title={modelALabel} dist={distA} />
      <Chart title={modelBLabel} dist={distB} />
    </div>
  );
}
