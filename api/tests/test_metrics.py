"""CENT-7 accept check: rankings + scatter endpoints against a seeded real
Postgres database (see conftest.py's seeded_client fixture)."""


def test_rankings_sorted_by_pagerank(seeded_client):
    resp = seeded_client.get("/api/metrics/rankings?sort=pagerank")
    assert resp.status_code == 200
    body = resp.json()
    assert [row["author_id"] for row in body] == [1, 2, 3]


def test_rankings_sorted_by_betweenness(seeded_client):
    resp = seeded_client.get("/api/metrics/rankings?sort=betweenness")
    assert resp.status_code == 200
    body = resp.json()
    assert [row["author_id"] for row in body] == [2, 1, 3]


def test_rankings_venue_filter(seeded_client):
    resp = seeded_client.get("/api/metrics/rankings?sort=pagerank&venue=journals/tkde")
    assert resp.status_code == 200
    body = resp.json()
    # Only Wei Wang (2) and Someone Else (3) have a journals/tkde paper;
    # Jane Smith (1) only ever published in conf/kdd.
    assert [row["author_id"] for row in body] == [2, 3]


def test_rankings_year_filter(seeded_client):
    resp = seeded_client.get("/api/metrics/rankings?sort=pagerank&year_from=2021&year_to=2021")
    assert resp.status_code == 200
    body = resp.json()
    # Only papers 2 (Jane Smith) and 3 (Wei Wang, Someone Else) are in 2021.
    assert {row["author_id"] for row in body} == {1, 2, 3}


def test_scatter(seeded_client):
    resp = seeded_client.get("/api/metrics/scatter")
    assert resp.status_code == 200
    body = {row["author_id"]: row for row in resp.json()}
    assert body[1]["pagerank_percentile"] == 100
    assert body[2]["betweenness_percentile"] == 100
    assert body[3]["pagerank_percentile"] == 0
