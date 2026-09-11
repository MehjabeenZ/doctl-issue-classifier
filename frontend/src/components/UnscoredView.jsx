import StatTile from "./StatTile";
import DistributionBars from "./DistributionBars";
import IssueTable from "./IssueTable";

export default function UnscoredView({ result }) {
  const { model_a_summary: a, model_b_summary: b, per_issue, agreement_rate } = result;
  const unscoredRows = per_issue.filter((r) => !r.ground_truth_label);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="muted" style={{ fontSize: 13 }}>
        No ground truth for these {unscoredRows.length} issues — this is the ambiguous backlog doctl maintainers never
        cleanly triaged. Agreement rate between the two models is the best available signal without a labeled answer.
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <StatTile label="Agreement rate (headline)" value={`${(agreement_rate * 100).toFixed(1)}%`} sub="both models, full corpus" />
      </div>
      <DistributionBars
        modelALabel={`${a.model_id} suggestions`}
        modelBLabel={`${b.model_id} suggestions`}
        distA={a.suggestion_distribution}
        distB={b.suggestion_distribution}
      />
      <div>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>Per-issue suggestions</div>
        <IssueTable rows={unscoredRows} modelALabel={a.model_id} modelBLabel={b.model_id} scored={false} />
      </div>
    </div>
  );
}
