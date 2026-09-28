"""GRAPH-1..4,7 accept check: real integration tests against a seeded real
Postgres database (see conftest.py's seeded_client fixture). GRAPH-5/6
(bridges toggle, time slider) are client-side only, using GRAPH-1's data -
no API to test here."""


def test_search_author_matches_substring_ranked_by_pagerank(seeded_client):
    resp = seeded_client.get("/api/graph/search-author?q=Wei")
    assert resp.status_code == 200
    assert resp.json() == [{"author_id": 2, "name": "Wei Wang 0001"}]


def test_coauthors_returns_all_seeded_nodes_and_edges(seeded_client):
    resp = seeded_client.get("/api/graph/coauthors?top=50")
    assert resp.status_code == 200
    body = resp.json()
    assert {n["author_id"] for n in body["nodes"]} == {1, 2, 3}
    edge_pairs = {(e["src"], e["dst"]) for e in body["edges"]}
    # Jane Smith(1)+Wei Wang(2) co-authored P1; Wei Wang(2)+Someone Else(3) co-authored P3.
    assert edge_pairs == {(1, 2), (2, 3)}


def test_ego_one_hop_from_jane_smith(seeded_client):
    resp = seeded_client.get("/api/graph/ego/1?hops=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["center"]["name"] == "Jane Smith"
    assert {n["author_id"] for n in body["nodes"]} == {1, 2}


def test_ego_two_hops_reaches_someone_else(seeded_client):
    resp = seeded_client.get("/api/graph/ego/1?hops=2")
    assert resp.status_code == 200
    body = resp.json()
    assert {n["author_id"] for n in body["nodes"]} == {1, 2, 3}


def test_ego_unknown_author_404s(seeded_client):
    resp = seeded_client.get("/api/graph/ego/9999?hops=1")
    assert resp.status_code == 404


def test_shortest_path_jane_to_someone_else_via_wei(seeded_client):
    resp = seeded_client.get("/api/graph/path?a=1&b=3")
    assert resp.status_code == 200
    body = resp.json()
    assert [n["author_id"] for n in body["path"]] == [1, 2, 3]
    assert len(body["hops"]) == 2
    assert body["hops"][0]["paper"]["dblp_key"] == "conf/kdd/P1"
    assert body["hops"][1]["paper"]["dblp_key"] == "journals/tkde/P3"


def test_shortest_path_same_author_is_trivial(seeded_client):
    resp = seeded_client.get("/api/graph/path?a=1&b=1")
    assert resp.status_code == 200
    assert resp.json() == {"path": [1], "hops": []}


def test_communities_groups_by_metric_community_and_ranks_keywords(seeded_client):
    resp = seeded_client.get("/api/graph/communities?top=50")
    assert resp.status_code == 200
    body = {row["community"]: row for row in resp.json()}
    assert body[1]["size"] == 2  # Jane Smith + Wei Wang
    assert body[2]["size"] == 1  # Someone Else
    # "graph" and "learning" appear in every seeded title - must be the top keywords.
    assert body[1]["top_keywords"][:2] == ["graph", "learning"]


def test_degree_distribution(seeded_client):
    resp = seeded_client.get("/api/graph/degree-dist")
    assert resp.status_code == 200
    body = {row["degree"]: row["authors"] for row in resp.json()}
    assert body == {1: 1, 2: 2}
