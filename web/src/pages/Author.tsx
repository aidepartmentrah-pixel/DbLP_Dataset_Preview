import { useParams, Link } from "react-router-dom";

import { useApi } from "../lib/useApi";

interface Paper {
  dblp_key: string;
  title: string;
  year: number;
  venue: string | null;
  venue_type: string | null;
}

interface Coauthor {
  author_id: number;
  name: string;
  weight: number;
}

interface AuthorProfile {
  author_id: number;
  name: string;
  orcid: string | null;
  pagerank: number | null;
  betweenness: number | null;
  pagerank_percentile: number | null;
  betweenness_percentile: number | null;
  degree: number | null;
  paper_count: number;
  papers: Paper[];
  coauthors: Coauthor[];
}

export default function Author() {
  const { authorId } = useParams();
  const state = useApi<AuthorProfile>(`/api/author/${authorId}`);

  if (state.status === "loading") return <div className="card chart-skeleton" style={{ height: 300 }} />;
  if (state.status === "error") return <div className="card"><p className="chart-empty">Author not found.</p></div>;
  if (state.status !== "ready") return null;

  const author = state.data;

  return (
    <div className="dashboard-grid">
      <div className="card chart-card span-12">
        <h2 className="chart-title">{author.name}</h2>
        {author.orcid && <p className="chart-subtitle">ORCID: {author.orcid}</p>}
        <dl className="node-drawer-facts" style={{ maxWidth: 400 }}>
          <dt>Papers</dt>
          <dd>{author.paper_count}</dd>
          <dt>Co-authors</dt>
          <dd>{author.degree ?? "—"}</dd>
          <dt>PageRank</dt>
          <dd>{author.pagerank_percentile != null ? `top ${(100 - author.pagerank_percentile).toFixed(1)}%` : "—"}</dd>
          <dt>Betweenness (bridge score)</dt>
          <dd>{author.betweenness_percentile != null ? `top ${(100 - author.betweenness_percentile).toFixed(1)}%` : "—"}</dd>
        </dl>
        <Link to={`/graph?ego=${author.author_id}`} className="node-drawer-link" style={{ display: "inline-block", width: "auto", textDecoration: "none" }}>
          View in Graph Explorer
        </Link>
      </div>

      <div className="card chart-card span-12">
        <h3 className="chart-title">Top co-authors</h3>
        {author.coauthors.length === 0 && <p className="chart-empty">No co-authors on record.</p>}
        {author.coauthors.length > 0 && (
          <div className="chat-citations">
            {author.coauthors.map((c) => (
              <Link key={c.author_id} to={`/author/${c.author_id}`} className="chat-citation-chip">
                {c.name} ({c.weight})
              </Link>
            ))}
          </div>
        )}
      </div>

      <div className="card chart-card span-12">
        <h3 className="chart-title">Papers ({author.paper_count})</h3>
        <table className="rankings-table">
          <thead>
            <tr><th>Year</th><th>Title</th><th>Venue</th></tr>
          </thead>
          <tbody>
            {author.papers.map((p) => (
              <tr key={p.dblp_key}>
                <td>{p.year}</td>
                <td>
                  <a href={`https://dblp.org/rec/${p.dblp_key}`} target="_blank" rel="noreferrer">
                    {p.title}
                  </a>
                </td>
                <td>{p.venue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
