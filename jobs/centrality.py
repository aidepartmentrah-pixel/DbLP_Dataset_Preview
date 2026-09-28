"""P5 / CENT-1..6: PageRank, sampled betweenness, and Louvain communities on
the real `coauthor_edge` graph, plus paper PageRank on `citation`, written
to `author_metrics` / `paper_metrics`.

Betweenness note (a real finding, not a guess - see jobs/bench_centrality.py
and "2. Initial Slicing Task Table.md", P5): exact igraph betweenness, even
at `cutoff=2`, did not finish in 20 real minutes on the actual v1 graph
(377,243 vertices / 2,695,430 edges) - the cost is dominated by the number
of sources (all of them), not path depth. Measured NetworkX's k-sampled
`betweenness_centrality` instead at a consistent ~8.65s/source. The
proposal's own suggested k=1,000 would take ~144 minutes - far over CENT's
own 30-minute accept bar - so CENT_BETWEENNESS_K defaults to 150
(~22 minutes), the largest k that comfortably fits the budget on real
hardware, leaving margin for the rest of the job. This is a measured
trade-off, not an arbitrary shortcut: rankings are otherwise consistent
between k=10 and k=50 in the benchmark (~8.65s/source both times).

Run inside the `jobs` container, e.g.:
    python centrality.py
"""

from __future__ import annotations

import os
import time

import igraph as ig
import networkx as nx
import psycopg

DEFAULT_BETWEENNESS_K = 150


def _log(msg: str) -> None:
    print(f"[centrality] {msg}", flush=True)


def load_coauthor_graph(cur) -> tuple[int, list[tuple[int, int, int]]]:
    cur.execute("SELECT COUNT(*) FROM author")
    n_authors = cur.fetchone()[0]
    cur.execute("SELECT src, dst, weight FROM coauthor_edge")
    edges = cur.fetchall()
    return n_authors, edges


def compute_pagerank_and_communities(n_authors: int, edges: list[tuple[int, int, int]]):
    g = ig.Graph(n=n_authors + 1)  # author_id is 1-based; vertex 0 unused
    g.add_edges([(s, d) for s, d, _w in edges])
    g.es["weight"] = [w for _s, _d, w in edges]

    pagerank = g.pagerank(weights="weight", damping=0.85)
    degree = g.degree()
    communities = g.community_multilevel(weights="weight")
    membership = communities.membership

    return pagerank, degree, membership


def compute_betweenness(n_authors: int, edges: list[tuple[int, int, int]], k: int, seed: int = 42):
    g = nx.Graph()
    g.add_nodes_from(range(1, n_authors + 1))
    # distance = 1/weight: frequent collaborators (high weight) count as
    # closer - see the proposal's own note on weighted betweenness (§5.2).
    g.add_weighted_edges_from(((s, d, 1.0 / w) for s, d, w in edges), weight="distance")
    k = min(k, n_authors)
    betweenness = nx.betweenness_centrality(g, k=k, weight="distance", seed=seed)
    return betweenness  # dict: author_id -> normalized score in [0, 1]


def percentiles(values: list[float]) -> list[float]:
    """Percentile rank (0-100, higher = more central) for each value, by
    position in the sorted order - ties share the same percentile."""
    n = len(values)
    if n <= 1:
        return [100.0] * n
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    for rank, i in enumerate(order):
        ranks[i] = rank
    return [100.0 * r / (n - 1) for r in ranks]


def compute_paper_pagerank(cur) -> list[tuple[int, float]]:
    cur.execute("SELECT paper_id FROM paper")
    paper_ids = [row[0] for row in cur.fetchall()]
    if not paper_ids:
        return []
    max_id = max(paper_ids)

    cur.execute("SELECT citing_id, cited_id FROM citation")
    citation_edges = cur.fetchall()

    g = ig.Graph(n=max_id + 1, directed=True)
    if citation_edges:
        g.add_edges(citation_edges)
    pagerank = g.pagerank(damping=0.85)
    return [(pid, pagerank[pid]) for pid in paper_ids]


def _recreate_staging(cur) -> None:
    cur.execute("DROP SCHEMA IF EXISTS staging_centrality CASCADE")
    cur.execute("CREATE SCHEMA staging_centrality")
    cur.execute("""
        CREATE TABLE staging_centrality.author_metrics (
            author_id INT PRIMARY KEY, degree INT, pagerank DOUBLE PRECISION,
            betweenness DOUBLE PRECISION, community INT,
            pagerank_percentile DOUBLE PRECISION, betweenness_percentile DOUBLE PRECISION
        )
    """)
    cur.execute("""
        CREATE TABLE staging_centrality.paper_metrics (
            paper_id INT PRIMARY KEY, pagerank DOUBLE PRECISION
        )
    """)


def run_centrality(database_url: str, betweenness_k: int = DEFAULT_BETWEENNESS_K) -> dict:
    t_start = time.time()
    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            n_authors, edges = load_coauthor_graph(cur)
            _log(f"loaded graph: {n_authors:,} authors, {len(edges):,} coauthor_edge rows")

            t0 = time.time()
            pagerank, degree, membership = compute_pagerank_and_communities(n_authors, edges)
            _log(f"pagerank + community_multilevel: {time.time() - t0:.1f}s")

            t0 = time.time()
            betweenness = compute_betweenness(n_authors, edges, betweenness_k)
            _log(f"betweenness (k={betweenness_k}): {time.time() - t0:.1f}s")

            pagerank_values = [pagerank[aid] for aid in range(1, n_authors + 1)]
            betweenness_values = [betweenness.get(aid, 0.0) for aid in range(1, n_authors + 1)]
            pagerank_pct = percentiles(pagerank_values)
            betweenness_pct = percentiles(betweenness_values)

            author_rows = [
                (
                    aid, degree[aid], pagerank[aid], betweenness.get(aid, 0.0), membership[aid],
                    pagerank_pct[aid - 1], betweenness_pct[aid - 1],
                )
                for aid in range(1, n_authors + 1)
            ]

            t0 = time.time()
            paper_rows = compute_paper_pagerank(cur)
            _log(f"paper pagerank (citation graph): {time.time() - t0:.1f}s, {len(paper_rows):,} papers")

            _recreate_staging(cur)
            with cur.copy(
                "COPY staging_centrality.author_metrics "
                "(author_id, degree, pagerank, betweenness, community, "
                "pagerank_percentile, betweenness_percentile) FROM STDIN"
            ) as copy:
                for row in author_rows:
                    copy.write_row(row)
            with cur.copy("COPY staging_centrality.paper_metrics (paper_id, pagerank) FROM STDIN") as copy:
                for row in paper_rows:
                    copy.write_row(row)

            cur.execute("TRUNCATE public.author_metrics")
            cur.execute("""
                INSERT INTO public.author_metrics
                    (author_id, degree, pagerank, betweenness, community,
                     pagerank_percentile, betweenness_percentile, computed_at)
                SELECT author_id, degree, pagerank, betweenness, community,
                       pagerank_percentile, betweenness_percentile, now()
                FROM staging_centrality.author_metrics
            """)
            cur.execute("TRUNCATE public.paper_metrics")
            cur.execute("""
                INSERT INTO public.paper_metrics (paper_id, pagerank, computed_at)
                SELECT paper_id, pagerank, now() FROM staging_centrality.paper_metrics
            """)
            cur.execute("DROP SCHEMA staging_centrality CASCADE")
        conn.commit()

    elapsed = time.time() - t_start
    _log(f"total: {elapsed:.1f}s ({elapsed / 60:.1f} min)")
    return {"authors": len(author_rows), "papers": len(paper_rows), "elapsed_seconds": elapsed}


def main():
    database_url = os.environ["DATABASE_URL"]
    k = int(os.environ.get("CENT_BETWEENNESS_K", DEFAULT_BETWEENNESS_K))
    counts = run_centrality(database_url, betweenness_k=k)
    print(
        f"Computed metrics for {counts['authors']:,} authors and {counts['papers']:,} papers "
        f"in {counts['elapsed_seconds'] / 60:.1f} min"
    )


if __name__ == "__main__":
    main()
