"""Shared fixture for DASH-1..7: seeds a real throwaway Postgres database
with known rows and points the FastAPI app's DB dependency at it, rather
than mocking the database layer - consistent with this project's preference
for real proof over mocks (see jobs/tests/test_etl.py for the same pattern).

Skips dependent tests if no live Postgres is reachable at DATABASE_URL
(e.g. running outside `docker compose up`).
"""

import os
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_session
from app.main import app

DB_INIT_DIR = Path("/db/init")


def _base_database_url() -> str:
    return os.environ.get("DATABASE_URL", "postgresql://dblp:dblp_dev_pw_2026@localhost:5432/dblp")


def _with_dbname(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture()
def seeded_client():
    admin_url = _base_database_url()
    test_url = _with_dbname(admin_url, "dblp_test_dashboard")

    try:
        conn = psycopg.connect(admin_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("no live Postgres reachable at DATABASE_URL - run inside `docker compose up`")

    with conn:
        with conn.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS dblp_test_dashboard")
            cur.execute("CREATE DATABASE dblp_test_dashboard")
    conn.close()

    with psycopg.connect(test_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            for name in ("001_schema.sql", "002_indexes.sql", "003_views.sql"):
                cur.execute((DB_INIT_DIR / name).read_text())

            cur.execute("""
                INSERT INTO venue (venue_id, key_prefix, name, type) VALUES
                    (1, 'conf/kdd', 'conf/kdd', 'conference'),
                    (2, 'journals/tkde', 'journals/tkde', 'journal')
            """)
            cur.execute("""
                INSERT INTO author (author_id, name, orcid) VALUES
                    (1, 'Jane Smith', '0000-0001-1000-1000'),
                    (2, 'Wei Wang 0001', NULL),
                    (3, 'Someone Else', NULL)
            """)
            cur.execute("""
                INSERT INTO paper (paper_id, dblp_key, title, year, type, venue_id, doi) VALUES
                    (1, 'conf/kdd/P1', 'Graph Learning at Scale', 2020, 'inproceedings', 1, '10.1/abc'),
                    (2, 'conf/kdd/P2', 'Graph Neural Networks', 2021, 'inproceedings', 1, NULL),
                    (3, 'journals/tkde/P3', 'A Survey of Graph Learning', 2021, 'article', 2, NULL),
                    (4, 'conf/kdd/P4', 'Graph Learning Revisited', 2019, 'inproceedings', 1, NULL)
            """)
            cur.execute("""
                INSERT INTO authorship (author_id, paper_id, "position") VALUES
                    (1, 1, 1), (2, 1, 2),
                    (1, 2, 1),
                    (2, 3, 1), (3, 3, 2),
                    (1, 4, 1)
            """)
            cur.execute("""
                INSERT INTO topic_year_counts (word, year, paper_count) VALUES
                    ('graph', 2020, 1), ('graph', 2021, 2), ('learning', 2020, 1)
            """)
            cur.execute("""
                INSERT INTO author_metrics
                    (author_id, degree, pagerank, betweenness, community,
                     pagerank_percentile, betweenness_percentile) VALUES
                    (1, 2, 0.5, 0.1, 1, 100, 50),
                    (2, 2, 0.3, 0.9, 1, 50, 100),
                    (3, 1, 0.2, 0.0, 2, 0, 0)
            """)
            # A real, DB-side now() (not a fixed literal) - graph.py's
            # adjacency cache is keyed on this value to invalidate when data
            # changes, and every test seeds a fresh database, so this must
            # be genuinely unique per test, not shared across them.
            cur.execute(
                "INSERT INTO etl_meta (id, loaded_at, papers_loaded, data_scope) "
                "VALUES (1, now(), 4, '2000:conf/kdd,journals/tkde')"
            )
            cur.execute("REFRESH MATERIALIZED VIEW coauthor_edge")

    test_engine = create_engine(test_url.replace("postgresql://", "postgresql+psycopg://", 1))
    TestSession = sessionmaker(bind=test_engine)

    def override_get_session():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        # Exposed for tests that need a direct DB session against the same
        # seeded test database (e.g. calling a helper function directly
        # rather than through an HTTP endpoint) - `app.db.SessionLocal`
        # would hit the real production database instead.
        client.test_session_factory = TestSession
        yield client

    app.dependency_overrides.pop(get_session, None)
    test_engine.dispose()

    conn = psycopg.connect(admin_url, autocommit=True)
    with conn:
        with conn.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS dblp_test_dashboard")
    conn.close()
