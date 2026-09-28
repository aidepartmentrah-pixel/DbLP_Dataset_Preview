import { useNavigate } from "react-router-dom";

import type { GraphNode } from "./graphBuild";

export default function NodeDrawer({ node, onClose }: { node: GraphNode; onClose: () => void }) {
  const navigate = useNavigate();
  return (
    <div className="card node-drawer">
      <button className="node-drawer-close" onClick={onClose} aria-label="Close">
        ×
      </button>
      <h3 className="chart-title">{node.name}</h3>
      <dl className="node-drawer-facts">
        <dt>Co-authors</dt>
        <dd>{node.degree}</dd>
        <dt>PageRank</dt>
        <dd>{node.pagerank.toExponential(2)}</dd>
        <dt>Betweenness</dt>
        <dd>{node.betweenness.toExponential(2)}</dd>
        <dt>Community</dt>
        <dd>{node.community}</dd>
      </dl>
      <button className="node-drawer-link" onClick={() => navigate(`/author/${node.author_id}`)}>
        Open author page
      </button>
    </div>
  );
}
