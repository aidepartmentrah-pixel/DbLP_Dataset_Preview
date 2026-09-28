import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";

export interface GraphNode {
  author_id: number;
  name: string;
  pagerank: number;
  betweenness: number;
  community: number;
  degree: number;
}

export interface GraphEdge {
  src: number;
  dst: number;
  weight: number;
  first_year: number | null;
  last_year: number | null;
}

const CATEGORICAL = ["--cat-1", "--cat-2", "--cat-3", "--cat-4", "--cat-5", "--cat-6"];
const GREY = "#94A3B8";

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/** §9.4: node size = sqrt(PageRank)-scaled 4-24px; colour = community, top 6
 * by size shown in the categorical palette, everything else grey. */
export function buildGraph(nodes: GraphNode[], edges: GraphEdge[]): Graph {
  const graph = new Graph({ multi: false, type: "undirected" });

  const communitySizes = new Map<number, number>();
  for (const n of nodes) communitySizes.set(n.community, (communitySizes.get(n.community) ?? 0) + 1);
  const topCommunities = [...communitySizes.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([id]) => id);
  const communityColor = new Map(topCommunities.map((id, i) => [id, cssVar(CATEGORICAL[i])]));

  const maxPagerank = Math.max(...nodes.map((n) => n.pagerank), 1e-12);
  const sizeFor = (pagerank: number) => 4 + 20 * Math.sqrt(Math.max(pagerank, 0) / maxPagerank);

  for (const n of nodes) {
    graph.addNode(n.author_id, {
      label: n.name,
      size: sizeFor(n.pagerank),
      color: communityColor.get(n.community) ?? GREY,
      x: Math.random(),
      y: Math.random(),
      pagerank: n.pagerank,
      betweenness: n.betweenness,
      community: n.community,
      degree: n.degree,
    });
  }

  const maxWeight = Math.max(...edges.map((e) => e.weight), 1);
  const borderColor = cssVar("--border");
  for (const e of edges) {
    if (!graph.hasNode(e.src) || !graph.hasNode(e.dst) || graph.hasEdge(e.src, e.dst)) continue;
    graph.addEdge(e.src, e.dst, {
      size: 0.5 + 3.5 * (e.weight / maxWeight),
      color: borderColor,
      first_year: e.first_year,
      weight: e.weight,
    });
  }

  forceAtlas2.assign(graph, { iterations: 100, settings: { gravity: 1, scalingRatio: 10 } });

  return graph;
}

/** §9.4 bridges toggle: fade everything except the top 5% by betweenness,
 * which turn amber. Mutates the graph's display attributes in place. */
export function applyBridgesToggle(graph: Graph, enabled: boolean, highlightColor: string): void {
  if (!enabled) {
    graph.forEachNode((node, attrs) => {
      graph.setNodeAttribute(node, "color", attrs.baseColor ?? attrs.color);
      graph.setNodeAttribute(node, "hidden", false);
    });
    return;
  }

  const scores = graph.nodes().map((n) => graph.getNodeAttribute(n, "betweenness") as number);
  const sorted = [...scores].sort((a, b) => a - b);
  const cutoff = sorted[Math.floor(sorted.length * 0.95)] ?? Infinity;

  graph.forEachNode((node, attrs) => {
    if (attrs.baseColor === undefined) graph.setNodeAttribute(node, "baseColor", attrs.color);
    const isBridge = (attrs.betweenness as number) >= cutoff;
    graph.setNodeAttribute(node, "color", isBridge ? highlightColor : attrs.baseColor);
  });
}

/** §9.4 time slider: show only edges with first_year <= the slider year. */
export function applyTimeFilter(graph: Graph, year: number | null): void {
  graph.forEachEdge((edge, attrs) => {
    const visible = year === null || attrs.first_year === null || attrs.first_year <= year;
    graph.setEdgeAttribute(edge, "hidden", !visible);
  });
}
