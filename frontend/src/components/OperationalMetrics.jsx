import StatTile from "./StatTile";

const usd = (v, digits = 4) => (v == null ? "n/a" : `$${v.toFixed(digits)}`);
const ms = (v) => `${v.toFixed(0)}ms`;

function ModelMetrics({ summary }) {
  const errTotal = summary.errors.rate_limit + summary.errors.timeout + summary.errors.parse_error + summary.errors.other;
  const errRate = summary.total_calls ? errTotal / summary.total_calls : 0;
  return (
    <div className="card" style={{ flex: 1, minWidth: 320 }}>
      <div style={{ fontWeight: 600, marginBottom: 12 }}>{summary.model_id}</div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <StatTile label="Cost / call" value={usd(summary.cost_per_call_usd)} />
        <StatTile label="Total cost" value={usd(summary.total_cost_usd, 2)} />
        <StatTile
          label="Full-run cost / correct"
          value={usd(summary.cost_per_correct_classification_usd)}
          sub={
            summary.cost_per_correct_classification_usd == null
              ? "no ground truth"
              : "total cost across all calls ÷ correct on the scored subset"
          }
        />
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 12 }}>
        <StatTile label="p50 latency" value={ms(summary.latency.p50_ms)} sub={`at concurrency ${summary.latency.concurrency_at_measurement}`} />
        <StatTile label="p95 latency" value={ms(summary.latency.p95_ms)} sub={`at concurrency ${summary.latency.concurrency_at_measurement}`} />
        <StatTile label="Wall-clock" value={`${summary.wall_clock_s.toFixed(1)}s`} />
        <StatTile label="Throughput" value={`${summary.throughput_rps.toFixed(2)} req/s`} />
      </div>
      <div>
        <div className="secondary" style={{ fontSize: 12, marginBottom: 6 }}>
          Error rate: {(errRate * 100).toFixed(1)}% ({errTotal} of {summary.total_calls})
        </div>
        <table>
          <thead><tr><th>rate limit</th><th>timeout</th><th>parse error</th><th>other</th></tr></thead>
          <tbody>
            <tr className="tabular-nums">
              <td>{summary.errors.rate_limit}</td>
              <td>{summary.errors.timeout}</td>
              <td>{summary.errors.parse_error}</td>
              <td>{summary.errors.other}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function OperationalMetrics({ result }) {
  return (
    <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
      <ModelMetrics summary={result.model_a_summary} />
      <ModelMetrics summary={result.model_b_summary} />
    </div>
  );
}
