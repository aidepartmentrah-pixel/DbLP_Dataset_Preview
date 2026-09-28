"""DASH-1..7 accept check: each endpoint against a seeded real Postgres
database (see conftest.py's seeded_client fixture for the fixed dataset)."""


def test_kpis(seeded_client):
    resp = seeded_client.get("/api/dashboard/kpis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["papers"] == 4
    assert body["authors"] == 3
    assert body["venues"] == 2
    assert body["last_update"] is not None


def test_papers_per_year(seeded_client):
    resp = seeded_client.get("/api/dashboard/papers-per-year")
    assert resp.status_code == 200
    by_year = {row["year"]: row for row in resp.json()}
    assert by_year[2019] == {"year": 2019, "journal": 0, "conference": 1, "other": 0}
    assert by_year[2020] == {"year": 2020, "journal": 0, "conference": 1, "other": 0}
    assert by_year[2021] == {"year": 2021, "journal": 1, "conference": 1, "other": 0}


def test_top_venues(seeded_client):
    resp = seeded_client.get("/api/dashboard/top-venues?limit=15")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0] == {"venue": "conf/kdd", "name": "conf/kdd", "type": "conference", "paper_count": 3}
    assert body[1] == {
        "venue": "journals/tkde", "name": "journals/tkde", "type": "journal", "paper_count": 1,
    }


def test_top_venues_year_filter(seeded_client):
    resp = seeded_client.get("/api/dashboard/top-venues?year_from=2021&year_to=2021")
    assert resp.status_code == 200
    body = resp.json()
    # Only conf/kdd/P2 and journals/tkde/P3 fall in 2021.
    assert {row["venue"]: row["paper_count"] for row in body} == {"conf/kdd": 1, "journals/tkde": 1}


def test_top_authors(seeded_client):
    resp = seeded_client.get("/api/dashboard/top-authors?limit=15")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0] == {"author_id": 1, "name": "Jane Smith", "paper_count": 3}
    names_by_count = {row["name"]: row["paper_count"] for row in body}
    assert names_by_count == {"Jane Smith": 3, "Wei Wang 0001": 2, "Someone Else": 1}


def test_team_size(seeded_client):
    resp = seeded_client.get("/api/dashboard/team-size")
    assert resp.status_code == 200
    by_year = {row["year"]: row for row in resp.json()}
    assert by_year[2019]["median"] == 1
    assert by_year[2020]["median"] == 2
    assert by_year[2021]["median"] == 1.5
    assert by_year[2021]["p25"] == 1.25
    assert by_year[2021]["p75"] == 1.75


def test_productivity(seeded_client):
    resp = seeded_client.get("/api/dashboard/productivity")
    assert resp.status_code == 200
    body = {row["papers"]: row["authors"] for row in resp.json()}
    assert body == {1: 1, 2: 1, 3: 1}


def test_topic_trends(seeded_client):
    resp = seeded_client.get("/api/dashboard/topic-trends")
    assert resp.status_code == 200
    body = {(row["word"], row["year"]): row["paper_count"] for row in resp.json()}
    assert body == {("graph", 2020): 1, ("graph", 2021): 2, ("learning", 2020): 1}
