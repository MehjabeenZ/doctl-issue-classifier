export default function StatTile({ label, value, sub }) {
  return (
    <div className="card" style={{ minWidth: 140 }}>
      <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>{label}</div>
      <div className="tabular-nums" style={{ fontSize: 26, fontWeight: 600 }}>{value}</div>
      {sub && <div className="secondary" style={{ fontSize: 12, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}
