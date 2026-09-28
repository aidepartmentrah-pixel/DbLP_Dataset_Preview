import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import AuthorSearchInput from "./graph/AuthorSearchInput";
import CommunityLegend from "./graph/CommunityLegend";
import DegreeDistChart from "./graph/DegreeDistChart";
import { applyBridgesToggle, applyTimeFilter, buildGraph, type GraphEdge, type GraphNode } from "./graph/graphBuild";
import NodeDrawer from "./graph/NodeDrawer";
import { useSigma } from "./graph/useSigma";

interface AuthorHit {
  author_id: number;
  name: string;
}

interface PathHop {
  from: { author_id: number; name: string };
  to: { author_id: number; name: string };
  paper: { dblp_key: string; title: string } | null;
}

type Mode = "network" | "ego" | "path";

export default function GraphExplorer() {
  const [searchParams] = useSearchParams();
  const egoParam = searchParams.get("ego");

  const [mode, setMode] = useState<Mode>(egoParam ? "ego" : "network");
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [egoTarget, setEgoTarget] = useState<AuthorHit | null>(null);
  const [pathA, setPathA] = useState<AuthorHit | null>(null);
  const [pathB, setPathB] = useState<AuthorHit | null>(null);
  const [pathHops, setPathHops] = useState<PathHop[] | null>(null);
  const [bridgesOn, setBridgesOn] = useState(false);
  const [timeYear, setTimeYear] = useState<number | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

  // P8: an author page's "View in Graph Explorer" link lands here as
  // `?ego=<id>` - look up that author's name once, then feed it into the
  // same ego-search state a manual search would produce.
  useEffect(() => {
    if (!egoParam) return;
    fetch(`/api/author/${egoParam}`)
      .then((r) => r.json())
      .then((data) => setEgoTarget({ author_id: data.author_id, name: data.name }))
      .catch(() => {});
  }, [egoParam]);

  useEffect(() => {
    setLoading(true);
    if (mode === "network") {
      fetch("/api/graph/coauthors?top=500")
        .then((r) => r.json())
        .then((data) => {
          setNodes(data.nodes);
          setEdges(data.edges);
          setLoading(false);
        });
    } else if (mode === "ego" && egoTarget) {
      fetch(`/api/graph/ego/${egoTarget.author_id}?hops=1`)
        .then((r) => r.json())
        .then((data) => {
          setNodes(data.nodes);
          setEdges(data.edges);
          setLoading(false);
        });
    } else if (mode === "path" && pathA && pathB) {
      Promise.all([
        fetch(`/api/graph/path?a=${pathA.author_id}&b=${pathB.author_id}`).then((r) => r.json()),
        fetch(`/api/graph/ego/${pathA.author_id}?hops=1`).then((r) => r.json()),
      ]).then(([pathData, egoData]) => {
        setPathHops(pathData.hops ?? []);
        setNodes(egoData.nodes);
        setEdges(egoData.edges);
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, [mode, egoTarget, pathA, pathB]);

  const graph = useMemo(() => (nodes.length > 0 ? buildGraph(nodes, edges) : null), [nodes, edges]);
  const years = edges.map((e) => e.first_year).filter((y): y is number => y !== null);
  const minYear = years.length ? Math.min(...years) : null;
  const maxYear = years.length ? Math.max(...years) : null;

  useEffect(() => {
    if (graph) applyBridgesToggle(graph, bridgesOn, "#F59E0B");
  }, [graph, bridgesOn]);

  useEffect(() => {
    if (graph) applyTimeFilter(graph, timeYear);
  }, [graph, timeYear]);

  const containerRef = useSigma(graph, (nodeId) => {
    const node = nodes.find((n) => String(n.author_id) === nodeId);
    if (node) setSelectedNode(node);
  });

  return (
    <div className="dashboard-grid">
      <div className="card chart-card span-12 filter-row graph-controls">
        <div className="graph-mode-tabs">
          {(["network", "ego", "path"] as Mode[]).map((m) => (
            <button key={m} className={mode === m ? "active" : ""} onClick={() => setMode(m)}>
              {m === "network" ? "Co-authorship network" : m === "ego" ? "Ego network" : "Shortest path"}
            </button>
          ))}
        </div>

        {mode === "ego" && (
          <AuthorSearchInput placeholder="Search an author..." onSelect={setEgoTarget} />
        )}
        {mode === "path" && (
          <>
            <AuthorSearchInput placeholder="From author..." onSelect={setPathA} />
            <AuthorSearchInput placeholder="To author..." onSelect={setPathB} />
          </>
        )}

        <label>
          <input type="checkbox" checked={bridgesOn} onChange={(e) => setBridgesOn(e.target.checked)} />
          {" "}Show bridges
        </label>

        {minYear !== null && maxYear !== null && minYear < maxYear && (
          <label>
            Up to year {timeYear ?? maxYear}
            <input
              type="range" min={minYear} max={maxYear} value={timeYear ?? maxYear}
              onChange={(e) => setTimeYear(Number(e.target.value))}
            />
          </label>
        )}
      </div>

      <div className="card chart-card span-12 graph-canvas-card">
        {loading && <div className="chart-skeleton" style={{ height: 520 }} />}
        {!loading && !graph && <p className="chart-empty">Pick an author to explore.</p>}
        {!loading && graph && <div ref={containerRef} className="sigma-canvas" />}
        {selectedNode && <NodeDrawer node={selectedNode} onClose={() => setSelectedNode(null)} />}
      </div>

      {mode === "path" && pathHops && (
        <div className="card chart-card span-12">
          <h3 className="chart-title">Path ({pathHops.length} hop{pathHops.length === 1 ? "" : "s"})</h3>
          {pathHops.length === 0 && <p>No path found within 6 hops.</p>}
          <ol>
            {pathHops.map((hop, i) => (
              <li key={i}>
                {hop.from.name} → {hop.to.name}
                {hop.paper && <> via "{hop.paper.title}" ({hop.paper.dblp_key})</>}
              </li>
            ))}
          </ol>
        </div>
      )}

      <DegreeDistChart />
      <CommunityLegend />
    </div>
  );
}
