"""DB-2 accept check: ETL loads a real fixture end-to-end into a real
Postgres database and is idempotent (re-running truncates/reloads cleanly,
not duplicating rows).

Uses a throwaway database on the same live `db` server (DATABASE_URL from
the environment, database name swapped for a test-only one) rather than
mocking psycopg, so this exercises the real COPY/staging-swap SQL path -
consistent with this project's own preference for real proof over mocks.
Skips itself if no live Postgres is reachable (e.g. running the fixture
tests alone, outside the `jobs` container / without `docker compose up`).
"""

import gzip
from pathlib import Path

import psycopg
import pytest

from etl import DEMO_DATA_SCOPE, compute_topic_trends, extract, parse_data_scope, run_etl

FIXTURES = Path(__file__).parent / "fixtures"
TEST_DATA_SCOPE = "2000:journals/tkde,conf/kdd"

DUPLICATE_AUTHOR_XML = b"""<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE dblp SYSTEM "dblp.dtd">
<dblp>
<inproceedings key="conf/kdd/Dup21" mdate="2021-01-01">
<author>Jane Smith</author>
<author>Jane Smith</author>
<title>A paper that lists one author twice.</title>
<year>2021</year>
<booktitle>KDD</booktitle>
</inproceedings>
</dblp>
"""


@pytest.fixture()
def sample_gz(tmp_path) -> Path:
    xml_bytes = (FIXTURES / "sample.xml").read_bytes()
    gz_path = tmp_path / "sample.xml.gz"
    with gzip.open(gz_path, "wb") as fh:
        fh.write(xml_bytes)
    return gz_path


@pytest.fixture()
def sample_dtd() -> Path:
    return FIXTURES / "sample.dtd"


def _base_database_url() -> str:
    import os

    return os.environ.get("DATABASE_URL", "postgresql://dblp:dblp_dev_pw_2026@localhost:5432/dblp")


def _with_dbname(url: str, dbname: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{dbname}"


@pytest.fixture
def test_db_url():
    admin_url = _base_database_url()
    test_url = _with_dbname(admin_url, "dblp_test_etl")

    try:
        conn = psycopg.connect(admin_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("no live Postgres reachable at DATABASE_URL - run inside `docker compose up`")

    with conn:
        with conn.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS dblp_test_etl")
            cur.execute("CREATE DATABASE dblp_test_etl")
    conn.close()

    schema_sql = (Path(__file__).parents[2] / "db" / "init" / "001_schema.sql").read_text()
    indexes_sql = (Path(__file__).parents[2] / "db" / "init" / "002_indexes.sql").read_text()
    views_sql = (Path(__file__).parents[2] / "db" / "init" / "003_views.sql").read_text()
    with psycopg.connect(test_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            cur.execute(indexes_sql)
            cur.execute(views_sql)

    yield test_url

    conn = psycopg.connect(admin_url, autocommit=True)
    with conn:
        with conn.cursor() as cur:
            cur.execute("DROP DATABASE IF EXISTS dblp_test_etl")
    conn.close()


def _counts(database_url: str) -> dict:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM venue")
            venues = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM author")
            authors = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM paper")
            papers = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM authorship")
            authorships = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM coauthor_edge")
            edges = cur.fetchone()[0]
            cur.execute("SELECT paper_count FROM v_kpis")
            kpi_papers = cur.fetchone()[0]
    return {
        "venues": venues, "authors": authors, "papers": papers,
        "authorships": authorships, "edges": edges, "kpi_papers": kpi_papers,
    }


def test_etl_loads_only_in_scope_records(test_db_url, sample_gz, sample_dtd):
    counts = run_etl(sample_gz, sample_dtd, TEST_DATA_SCOPE, test_db_url)

    # In-scope: journals/tkde/Smith21 (2021, 2 authors), conf/kdd/Smith21
    # (2021, 2 authors), conf/kdd/Wang22 (2022, 1 author).
    # Excluded: journals/tkde/Old99 (1999, before start_year 2000), and the
    # bare `proceedings` record (not a paper).
    assert counts["papers"] == 3
    assert counts["venues"] == 2
    # Distinct authors: Jane Smith (orcid), Wei Wang 0001 (name), Someone
    # NoOrcid (name) = 3. "W. Wang" only ever appears in the excluded `www`
    # record, which the ETL doesn't read authors from at all.
    assert counts["authors"] == 3
    assert counts["authorships"] == 5

    db_counts = _counts(test_db_url)
    assert db_counts["papers"] == 3
    assert db_counts["venues"] == 2
    assert db_counts["authors"] == 3
    assert db_counts["authorships"] == 5
    assert db_counts["kpi_papers"] == 3
    # coauthor_edge: Jane Smith + Wei Wang 0001 on journals/tkde/Smith21, and
    # Jane Smith + Someone NoOrcid on conf/kdd/Smith21 -> 2 distinct pairs.
    # conf/kdd/Wang22 has a single author, so it contributes no pair.
    assert db_counts["edges"] == 2


def test_etl_is_idempotent(test_db_url, sample_gz, sample_dtd):
    first = run_etl(sample_gz, sample_dtd, TEST_DATA_SCOPE, test_db_url)
    second = run_etl(sample_gz, sample_dtd, TEST_DATA_SCOPE, test_db_url)

    assert first == second
    db_counts = _counts(test_db_url)
    assert db_counts["papers"] == 3
    assert db_counts["authors"] == 3
    assert db_counts["authorships"] == 5


def test_extract_dedupes_author_listed_twice_on_same_paper(tmp_path):
    """Real bug found running the ETL against the full dblp dump: a small
    number of records list the same author twice in one <author> list,
    which collides on authorship's (author_id, paper_id) primary key if
    not deduplicated per paper."""
    gz_path = tmp_path / "dup.xml.gz"
    with gzip.open(gz_path, "wb") as fh:
        fh.write(DUPLICATE_AUTHOR_XML)
    dtd_path = FIXTURES / "sample.dtd"

    extracted = extract(gz_path, dtd_path, 2000, {"conf/kdd"})

    assert len(extracted.papers) == 1
    assert len(extracted.authors) == 1
    assert extracted.authorships == [(1, 1, 1)]


def test_compute_topic_trends_ranks_by_paper_presence_not_raw_frequency():
    # (paper_id, dblp_key, title, year, type, venue_id, doi)
    papers = [
        (1, "k1", "Graph Neural Networks for Graph Classification", 2020, "article", 1, None),
        (2, "k2", "Graph Learning at Scale", 2021, "article", 1, None),
        (3, "k2", "A Survey of Graph Learning Methods", 2021, "article", 1, None),
    ]
    trends = compute_topic_trends(papers, top_n=2)

    # "graph" appears in all 3 titles (twice in title 1, but counted once
    # per paper) -> present in 3 papers. "learning" appears in 2 papers.
    # Common filler ("survey", "methods") must not crowd out real keywords.
    words = {w for w, _year, _count in trends}
    assert words == {"graph", "learning"}
    assert ("graph", 2020, 1) in trends
    assert ("graph", 2021, 2) in trends
    assert ("learning", 2021, 2) in trends


def test_demo_data_scope_is_a_real_parseable_scope():
    """P8: DEMO=1 must parse to a real start year and a non-empty, well-
    formed venue set - the real paper count (20,501, queried directly
    against the loaded v1 data) is recorded in etl.py's own comment and
    "2. Initial Slicing Task Table.md", not re-asserted here since it would
    need the full live dataset loaded to check."""
    start_year, venues = parse_data_scope(DEMO_DATA_SCOPE)
    assert start_year == 2018
    assert venues == {
        "conf/kdd", "conf/sigmod", "conf/vldb", "conf/icde",
        "conf/wsdm", "conf/sigir", "conf/cikm",
    }
