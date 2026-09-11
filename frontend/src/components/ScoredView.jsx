import StatTile from "./StatTile";
import ConfusionMatrix from "./ConfusionMatrix";
import IssueTable from "./IssueTable";
import { LABELS } from "../labels";

const pct = (v) => (v == null ? "n/a" : `${(v * 100).toFixed(1)}%`);

function PerClassTable({ summary }) {
  return (
    <div className="card">
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{summary.model_id} — per-class</div>
      <table>
        <thead>
          <tr><th>class</th><th>support</th><th>precision</th><th>recall</th><th>F1</th></tr>
        </thead>
        <tbody>
          {LABELS.map((l) => {
            const support = summary.support_by_class?.[l] ?? 0;
            const noData = support === 0;
            return (
              <tr key={l}>
                <td>{l}</td>
                <td className="tabular-nums muted">{noData ? "no data" : support}</td>
                <td className="tabular-nums">{noData ? "—" : pct(summary.precision_by_class?.[l])}</td>
                <td className="tabular-nums">{noData ? "—" : pct(summary.recall_by_class?.[l])}</td>
                <td className="tabular-nums">{noData ? "—" : pct(summary.f1_by_class?.[l])}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function ScoredView({ result }) {
  const { model_a_summary: a, model_b_summary: b, per_issue } = result;
  const scoredRows = per_issue.filter((r) => r.ground_truth_label);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="muted" style={{ fontSize: 13 }}>
        Scored against ground truth for {scoredRows.length} issues (see README for how this subset was constructed —
        documentation/other have no ground-truth examples, so those rows show "no data" rather than a misleading 0%).
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <StatTile label={`${a.model_id} accuracy`} value={pct(a.accuracy)} />
        <StatTile label={`${b.model_id} accuracy`} value={pct(b.accuracy)} />
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <ConfusionMatrix title={`${a.model_id} confusion matrix`} matrix={a.confusion_matrix} supportByClass={a.support_by_class} />
        <ConfusionMatrix title={`${b.model_id} confusion matrix`} matrix={b.confusion_matrix} supportByClass={b.support_by_class} />
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <PerClassTable summary={a} />
        <PerClassTable summary={b} />
      </div>
      <div>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Drill-down (scored issues, ground truth visible)</div>
        <IssueTable rows={scoredRows} modelALabel={a.model_id} modelBLabel={b.model_id} scored />
      </div>
    </div>
  );
}
