"""P2 / DB-2: dblp XML -> filtered in-memory rows -> COPY into PostgreSQL.

Filters to DATA_SCOPE (a start year and a set of dblp venue key prefixes,
chosen for real in P1 - see reports/dblp_profile.md). Idempotent via a
truncate-and-swap staging pattern (Technical Proposal §3.3 step 4, §8.1
DB-2): rows are COPY'd into a `staging` schema first, and only swapped into
the real tables (inside one transaction) once every staging table has
loaded cleanly. Re-running always reproduces the same real tables, whether
it's the first load or the hundredth.

Run inside the `jobs` container, e.g.:
    python etl.py --xml /data/dblp.xml.gz --dtd /data/dblp.dtd
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter
from pathlib import Path

import psycopg

from dblp_xml import author_key, child_text, element_text, stream_records, venue_prefix

PAPER_TAGS = ("article", "inproceedings")

_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/")

# DASH-7 (topic trends): a plain per-request SQL scan/tokenize of all titles
# measured at ~800ms on the real v1 data - over the 500ms endpoint budget -
# so keyword x year counts are precomputed here (titles are already in
# memory during the ETL pass) into a small table the API just SELECTs from.
_TITLE_WORD_RE = re.compile(r"[a-zA-Z]+")
_TOPIC_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "using", "based",
    "towards", "toward", "into", "over", "under", "between", "within",
    "without", "about", "study", "survey", "approach", "approaches",
    "method", "methods", "analysis", "system", "systems", "new", "novel",
    "case", "paper", "review", "part", "large", "small", "efficient",
    "effective", "robust", "scalable", "fast", "simple", "framework",
    "models", "model", "its", "are", "can", "not", "all", "more", "most",
    "some", "such", "these", "those", "their", "our", "your", "you", "when",
    "where", "what", "how", "why", "which", "who", "whom", "have", "has",
    "had", "been", "being", "was", "were", "will", "would", "should",
    "could", "may", "might", "must", "than", "then", "also", "both", "each",
    "other", "only", "own", "same", "too", "very", "just", "one", "two",
    "three", "first", "second", "third", "per", "use", "used",
}
_TOPIC_TOP_N = 20


def _tokenize_title(title: str) -> set[str]:
    return {
        w for w in (m.group(0).lower() for m in _TITLE_WORD_RE.finditer(title))
        if len(w) > 3 and w not in _TOPIC_STOPWORDS
    }


def compute_topic_trends(papers: list[tuple], top_n: int = _TOPIC_TOP_N) -> list[tuple]:
    """papers: (paper_id, dblp_key, title, year, type, venue_id, doi) rows.
    Counts each word at most once per paper (paper-level presence), so a
    title repeating a word doesn't inflate its trend."""
    word_totals: Counter[str] = Counter()
    word_year_counts: Counter[tuple[str, int]] = Counter()
    for _, _, title, year, _type, _venue_id, _doi in papers:
        for word in _tokenize_title(title):
            word_totals[word] += 1
            word_year_counts[(word, year)] += 1

    top_words = {w for w, _ in word_totals.most_common(top_n)}
    return sorted(
        (word, year, count)
        for (word, year), count in word_year_counts.items()
        if word in top_words
    )


def parse_data_scope(raw: str) -> tuple[int, set[str]]:
    """DATA_SCOPE format: "<start_year>:<comma-separated venue key prefixes>"."""
    start_year_str, venues_str = raw.split(":", 1)
    venues = {v.strip() for v in venues_str.split(",") if v.strip()}
    if not venues:
        raise ValueError(f"DATA_SCOPE has no venues: {raw!r}")
    return int(start_year_str), venues


def venue_type(prefix: str) -> str:
    if prefix.startswith("conf/"):
        return "conference"
    if prefix.startswith("journals/"):
        return "journal"
    return "other"


def extract_doi(ee: str | None) -> str | None:
    if not ee:
        return None
    for p in _DOI_PREFIXES:
        if ee.startswith(p):
            return ee[len(p):]
    return None


class _Extracted:
    """Rows extracted from the XML, with sequential integer ids assigned as
    each venue/author/paper is first seen (deterministic, single pass)."""

    def __init__(self):
        self.venue_ids: dict[str, int] = {}
        self.venues: list[tuple] = []  # (venue_id, key_prefix, name, type)

        self.author_ids: dict[str, int] = {}
        self.authors: list[tuple] = []  # (author_id, name, orcid)

        self.papers: list[tuple] = []  # (paper_id, dblp_key, title, year, type, venue_id, doi)
        self.authorships: list[tuple] = []  # (author_id, paper_id, position)
        self.topic_trends: list[tuple] = []  # (word, year, paper_count), set after extraction

    def get_venue_id(self, prefix: str) -> int:
        vid = self.venue_ids.get(prefix)
        if vid is None:
            vid = len(self.venue_ids) + 1
            self.venue_ids[prefix] = vid
            self.venues.append((vid, prefix, prefix, venue_type(prefix)))
        return vid

    def get_author_id(self, author_elem) -> int:
        ak = author_key(author_elem)
        aid = self.author_ids.get(ak)
        if aid is None:
            aid = len(self.author_ids) + 1
            self.author_ids[ak] = aid
            orcid = author_elem.get("orcid")
            name = element_text(author_elem)
            self.authors.append((aid, name, orcid))
        return aid


def extract(xml_path: Path, dtd_path: Path, start_year: int, scope_venues: set[str]) -> _Extracted:
    out = _Extracted()
    next_paper_id = 1

    for elem in stream_records(xml_path, dtd_path):
        if elem.tag not in PAPER_TAGS:
            continue
        key = elem.get("key")
        if not key:
            continue
        prefix = venue_prefix(key)
        if prefix not in scope_venues:
            continue
        year_text = elem.findtext("year")
        if not year_text or not year_text.strip().isdigit():
            continue
        year = int(year_text)
        if year < start_year:
            continue

        venue_id = out.get_venue_id(prefix)
        title = child_text(elem, "title") or ""
        doi = extract_doi(elem.findtext("ee"))

        paper_id = next_paper_id
        next_paper_id += 1
        out.papers.append((paper_id, key, title, year, elem.tag, venue_id, doi))

        # Real dblp data quirk: a handful of records list the same author
        # twice in one <author> list (same name/orcid twice), which would
        # otherwise collide on authorship's (author_id, paper_id) primary
        # key. Keep the first occurrence's position, drop the repeat.
        seen_author_ids: set[int] = set()
        for position, author_elem in enumerate(elem.findall("author"), start=1):
            author_id = out.get_author_id(author_elem)
            if author_id in seen_author_ids:
                continue
            seen_author_ids.add(author_id)
            out.authorships.append((author_id, paper_id, position))

    out.topic_trends = compute_topic_trends(out.papers)
    return out


def _recreate_staging(cur: psycopg.Cursor) -> None:
    cur.execute("DROP SCHEMA IF EXISTS staging CASCADE")
    cur.execute("CREATE SCHEMA staging")
    cur.execute("""
        CREATE TABLE staging.venue (
            venue_id INT PRIMARY KEY, key_prefix TEXT, name TEXT, type TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE staging.author (
            author_id INT PRIMARY KEY, name TEXT, orcid TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE staging.paper (
            paper_id INT PRIMARY KEY, dblp_key TEXT, title TEXT,
            year SMALLINT, type TEXT, venue_id INT, doi TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE staging.authorship (
            author_id INT, paper_id INT, "position" SMALLINT
        )
    """)
    cur.execute("""
        CREATE TABLE staging.topic_year_counts (
            word TEXT, year SMALLINT, paper_count INT
        )
    """)


def _copy_rows(cur: psycopg.Cursor, table: str, columns: str, rows: list[tuple]) -> None:
    with cur.copy(f"COPY {table} ({columns}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)


def _swap_into_public(cur: psycopg.Cursor, data_scope_raw: str, papers_loaded: int) -> None:
    cur.execute("TRUNCATE public.venue, public.author, public.paper CASCADE")
    cur.execute("INSERT INTO public.venue (venue_id, key_prefix, name, type) SELECT * FROM staging.venue")
    cur.execute("INSERT INTO public.author (author_id, name, orcid) SELECT * FROM staging.author")
    cur.execute(
        "INSERT INTO public.paper (paper_id, dblp_key, title, year, type, venue_id, doi) "
        "SELECT * FROM staging.paper"
    )
    cur.execute(
        'INSERT INTO public.authorship (author_id, paper_id, "position") '
        'SELECT * FROM staging.authorship'
    )
    for table, id_col in (("venue", "venue_id"), ("author", "author_id"), ("paper", "paper_id")):
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('public.{table}', '{id_col}'), "
            f"COALESCE((SELECT MAX({id_col}) FROM public.{table}), 1))"
        )
    cur.execute("TRUNCATE public.topic_year_counts")
    cur.execute(
        "INSERT INTO public.topic_year_counts (word, year, paper_count) "
        "SELECT * FROM staging.topic_year_counts"
    )
    cur.execute("REFRESH MATERIALIZED VIEW public.coauthor_edge")
    cur.execute(
        "INSERT INTO public.etl_meta (id, loaded_at, papers_loaded, data_scope) "
        "VALUES (1, now(), %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET loaded_at = now(), papers_loaded = EXCLUDED.papers_loaded, "
        "data_scope = EXCLUDED.data_scope",
        (papers_loaded, data_scope_raw),
    )
    cur.execute("DROP SCHEMA staging CASCADE")


def run_etl(xml_path: Path, dtd_path: Path, data_scope_raw: str, database_url: str) -> dict:
    start_year, scope_venues = parse_data_scope(data_scope_raw)
    extracted = extract(xml_path, dtd_path, start_year, scope_venues)

    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            _recreate_staging(cur)
            _copy_rows(cur, "staging.venue", "venue_id, key_prefix, name, type", extracted.venues)
            _copy_rows(cur, "staging.author", "author_id, name, orcid", extracted.authors)
            _copy_rows(
                cur, "staging.paper",
                "paper_id, dblp_key, title, year, type, venue_id, doi",
                extracted.papers,
            )
            _copy_rows(
                cur, "staging.authorship", 'author_id, paper_id, "position"',
                extracted.authorships,
            )
            _copy_rows(
                cur, "staging.topic_year_counts", "word, year, paper_count",
                extracted.topic_trends,
            )
            _swap_into_public(cur, data_scope_raw, len(extracted.papers))
        conn.commit()

    return {
        "venues": len(extracted.venues),
        "authors": len(extracted.authors),
        "papers": len(extracted.papers),
        "authorships": len(extracted.authorships),
    }


# P8 (polish): DEMO=1 loads this instead of the real .env DATA_SCOPE, so
# `docker compose up` + one ETL run can be walked end to end (including
# centrality and embedding, both far slower at full v1 scale) without a
# multi-hour wait. Real, evidence-based pick, not an arbitrary shrink: these
# 7 database/data-mining venues since 2018 total 20,501 real papers (queried
# directly against the loaded v1 data) - a coherent, recognizable field at
# the proposal's own suggested demo size (§10: "~20k papers").
DEMO_DATA_SCOPE = "2018:conf/kdd,conf/sigmod,conf/vldb,conf/icde,conf/wsdm,conf/sigir,conf/cikm"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml", type=Path, default=Path("/data/dblp.xml.gz"))
    ap.add_argument("--dtd", type=Path, default=Path("/data/dblp.dtd"))
    ap.add_argument("--data-scope", default=os.environ.get("DATA_SCOPE", ""))
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL", ""))
    args = ap.parse_args()

    if os.environ.get("DEMO") == "1":
        args.data_scope = DEMO_DATA_SCOPE
        print(f"[etl] DEMO=1: using the demo scope ({DEMO_DATA_SCOPE})", flush=True)

    if not args.data_scope:
        raise SystemExit("DATA_SCOPE is required (set the env var or pass --data-scope)")
    if not args.database_url:
        raise SystemExit("DATABASE_URL is required (set the env var or pass --database-url)")

    counts = run_etl(args.xml, args.dtd, args.data_scope, args.database_url)
    print(
        f"Loaded {counts['papers']:,} papers, {counts['authors']:,} authors, "
        f"{counts['venues']:,} venues, {counts['authorships']:,} authorship rows"
    )


if __name__ == "__main__":
    main()
