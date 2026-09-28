import { useNavigate } from "react-router-dom";

import { useApi } from "../../lib/useApi";

interface RankingRow {
  author_id: number;
  name: string;
  pagerank: number;
  betweenness: number;
  degree: number;
  pagerank_percentile: number;
  betweenness_percentile: number;
}

interface RankingsTableProps {
  sort: "pagerank" | "betweenness";
  title: string;
  venue: string;
  yearFrom: string;
  yearTo: string;
}

export default function RankingsTable({ sort, title, venue, yearFrom, yearTo }: RankingsTableProps) {
  const navigate = useNavigate();
  const params = new URLSearchParams({ sort, limit: "50" });
  if (venue) params.set("venue", venue);
  if (yearFrom) params.set("year_from", yearFrom);
  if (yearTo) params.set("year_to", yearTo);

  const state = useApi<RankingRow[]>(`/api/metrics/rankings?${params.toString()}`, (d) => d.length === 0);

  return (
    <div className="card chart-card">
      <h3 className="chart-title">{title}</h3>
      {state.status === "loading" && <div className="chart-skeleton" />}
      {state.status === "error" && <p className="chart-empty">Couldn't load: {state.error}</p>}
      {state.status === "empty" && <p className="chart-empty">No data yet - run the centrality job.</p>}
      {state.status === "ready" && (
        <table className="rankings-table">
          <thead>
            <tr>
              <th>#</th><th>Author</th><th>{sort === "pagerank" ? "PageRank" : "Betweenness"}</th><th>Percentile</th>
            </tr>
          </thead>
          <tbody>
            {state.data.map((row, i) => (
              <tr key={row.author_id} onClick={() => navigate(`/author/${row.author_id}`)}>
                <td>{i + 1}</td>
                <td>{row.name}</td>
                <td>{(sort === "pagerank" ? row.pagerank : row.betweenness).toFixed(4)}</td>
                <td>{Math.round(sort === "pagerank" ? row.pagerank_percentile : row.betweenness_percentile)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
