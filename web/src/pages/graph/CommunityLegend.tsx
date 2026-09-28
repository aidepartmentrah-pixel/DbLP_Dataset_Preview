import { useApi } from "../../lib/useApi";

interface CommunityRow {
  community: number;
  size: number;
  top_keywords: string[];
}

export default function CommunityLegend() {
  const state = useApi<CommunityRow[]>("/api/graph/communities?top=500", (d) => d.length === 0);
  if (state.status !== "ready") return null;

  return (
    <div className="card chart-card span-12">
      <h3 className="chart-title">Communities</h3>
      <p className="chart-subtitle">Louvain communities in the current view, by size</p>
      <table className="rankings-table">
        <thead>
          <tr><th>Community</th><th>Size</th><th>Top keywords</th></tr>
        </thead>
        <tbody>
          {state.data.map((c) => (
            <tr key={c.community}>
              <td>{c.community}</td>
              <td>{c.size}</td>
              <td>{c.top_keywords.join(", ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
