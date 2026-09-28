"""CENT accept check: unit tests on toy graphs with known PageRank/
betweenness properties (a star graph, a bridge graph), per the proposal's
own Core automated proof for P5."""

from centrality import compute_betweenness, compute_pagerank_and_communities, percentiles

# Star graph: center=1, leaves=2..5. Every shortest path between two leaves
# passes through the center, so its betweenness should be (close to) the
# maximum possible (1.0, normalized) and strictly greater than any leaf's
# (which should be 0: no shortest path between two other nodes ever
# passes through a leaf).
STAR_EDGES = [(1, 2, 1), (1, 3, 1), (1, 4, 1), (1, 5, 1)]
STAR_N = 5

# Bridge graph: two triangles {1,2,3} and {4,5,6} joined by a single edge
# (3,4). Every shortest path between the two triangles must cross that
# bridge, so nodes 3 and 4 should have strictly higher betweenness than the
# non-bridge nodes 1, 2, 5, 6.
BRIDGE_EDGES = [
    (1, 2, 1), (1, 3, 1), (2, 3, 1),
    (4, 5, 1), (4, 6, 1), (5, 6, 1),
    (3, 4, 1),
]
BRIDGE_N = 6


def test_star_graph_center_has_max_pagerank_and_betweenness():
    pagerank, degree, _membership = compute_pagerank_and_communities(STAR_N, STAR_EDGES)
    betweenness = compute_betweenness(STAR_N, STAR_EDGES, k=STAR_N)  # k=n -> exact

    assert degree[1] == 4
    assert pagerank[1] > max(pagerank[2:])  # center strictly beats every leaf
    assert betweenness[1] == 1.0  # every leaf-leaf shortest path crosses it
    for leaf in (2, 3, 4, 5):
        assert betweenness.get(leaf, 0.0) == 0.0


def test_bridge_graph_bridge_nodes_have_higher_betweenness():
    betweenness = compute_betweenness(BRIDGE_N, BRIDGE_EDGES, k=BRIDGE_N)  # exact

    bridge_scores = [betweenness[3], betweenness[4]]
    non_bridge_scores = [betweenness.get(n, 0.0) for n in (1, 2, 5, 6)]

    assert min(bridge_scores) > max(non_bridge_scores)


def test_bridge_graph_communities_split_at_the_bridge():
    _pagerank, _degree, membership = compute_pagerank_and_communities(BRIDGE_N, BRIDGE_EDGES)

    # Two triangles connected by one weak link should form two communities,
    # with the two triangles' own members grouped together.
    assert membership[1] == membership[2] == membership[3]
    assert membership[4] == membership[5] == membership[6]
    assert membership[1] != membership[4]


def test_percentiles_ranks_lowest_to_highest():
    assert percentiles([10, 30, 20]) == [0.0, 100.0, 50.0]


def test_percentiles_single_value():
    assert percentiles([42]) == [100.0]
