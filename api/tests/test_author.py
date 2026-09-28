"""P8 accept check: the author profile endpoint, against a seeded real
Postgres database (see conftest.py's seeded_client fixture)."""


def test_author_profile_returns_metrics_papers_and_coauthors(seeded_client):
    resp = seeded_client.get("/api/author/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Jane Smith"
    assert body["pagerank"] == 0.5
    assert body["paper_count"] == 3
    dblp_keys = {p["dblp_key"] for p in body["papers"]}
    assert dblp_keys == {"conf/kdd/P1", "conf/kdd/P2", "conf/kdd/P4"}
    coauthor_names = {c["name"] for c in body["coauthors"]}
    assert coauthor_names == {"Wei Wang 0001"}


def test_author_profile_unknown_author_404s(seeded_client):
    resp = seeded_client.get("/api/author/9999")
    assert resp.status_code == 404
