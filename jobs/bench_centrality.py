"""One-off benchmark (not part of the pipeline): measures real timing on the
actual v1 coauthor_edge graph. CENT-3's accept bar (the whole job under 30
min) makes betweenness the one real risk - exact igraph betweenness, and
even igraph's `cutoff=2` (paths of at most 2 hops), did not finish in 20
real minutes on this graph (377,243 vertices / 2,695,430 edges): the cost is
dominated by the number of *sources* (all 377k vertices), not path depth.
So this benchmarks the proposal's own documented fallback instead: NetworkX
`betweenness_centrality(G, k=...)`, sampling from a small, fixed number of
random sources and scaling up - timed here at small k to extrapolate a real
k that fits the 30-minute job budget, rather than guessing one.
"""

import os
import time

import networkx as nx
import psycopg

url = os.environ["DATABASE_URL"]
with psycopg.connect(url) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM author")
        n_authors = cur.fetchone()[0]
        cur.execute("SELECT src, dst, weight FROM coauthor_edge")
        edges = cur.fetchall()

print(f"authors (vertices): {n_authors:,}", flush=True)
print(f"coauthor_edge rows: {len(edges):,}", flush=True)

t0 = time.time()
g = nx.Graph()
g.add_nodes_from(range(1, n_authors + 1))
# distance = 1/weight: frequent collaborators (high weight) count as closer,
# per the proposal's own note on weighted betweenness.
g.add_weighted_edges_from(((s, d, 1.0 / w) for s, d, w in edges), weight="distance")
print(f"networkx graph build: {time.time() - t0:.1f}s", flush=True)

for k in (10, 50):
    t0 = time.time()
    nx.betweenness_centrality(g, k=k, weight="distance", seed=42)
    elapsed = time.time() - t0
    print(f"betweenness k={k}: {elapsed:.1f}s ({elapsed / k:.3f}s/source)", flush=True)
