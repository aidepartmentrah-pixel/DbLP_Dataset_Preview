"""CHAT-2: the three retrieval tools (§6.4), as plain Python functions with
JSON schemas for Ollama's tool-calling. `sql_query` runs through
DATABASE_URL_READONLY (see db/init/004_readonly_role.sql) - a real,
separate Postgres role with SELECT-only grants, not just an app convention -
so a bug in a template (or a careless future addition) can't write to the
database no matter what. Every query also gets a 5s statement_timeout.
"""

from __future__ import annotations

import os

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

_READONLY_URL = os.environ.get("DATABASE_URL_READONLY", "")
_readonly_engine = (
    create_engine(_READONLY_URL.replace("postgresql://", "postgresql+psycopg://", 1))
    if _READONLY_URL else None
)
ReadOnlySession = sessionmaker(bind=_readonly_engine) if _readonly_engine else None

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")

# ---------------------------------------------------------------------------
# sql_query: ~15 fixed, parameterised templates (§6.4) - free text-to-SQL is
# explicitly out of scope for v1 (§6.4: "safer and easier to test").
# ---------------------------------------------------------------------------

SQL_TEMPLATES: dict[str, str] = {
    "kpis": "SELECT * FROM v_kpis",
    "papers_per_year": (
        "SELECT year, SUM(paper_count) AS papers FROM v_papers_per_year "
        "WHERE (CAST(:year_from AS SMALLINT) IS NULL OR year >= CAST(:year_from AS SMALLINT)) "
        "AND (CAST(:year_to AS SMALLINT) IS NULL OR year <= CAST(:year_to AS SMALLINT)) "
        "GROUP BY year ORDER BY year"
    ),
    "top_venues": "SELECT key_prefix, name, type, SUM(paper_count) AS papers FROM v_top_venues GROUP BY key_prefix, name, type ORDER BY papers DESC LIMIT :limit",
    # Real gap found via the CHAT-7 eval: no existing template answers "how
    # many total papers has venue X published (across all years)?" -
    # top_venues only ranks ALL venues, and papers_in_venue_year requires an
    # exact year. The model correctly tried several wrong templates for this
    # shape of question, got real errors back, and (correctly, per CHAT-6)
    # refused to fabricate a number rather than guessing - a real symptom of
    # this real gap, not a hallucination-safety failure.
    "papers_by_venue": (
        "SELECT key_prefix, SUM(paper_count) AS papers FROM v_top_venues "
        "WHERE key_prefix = :venue GROUP BY key_prefix"
    ),
    "top_authors_by_papers": (
        "SELECT a.name, p.paper_count FROM v_author_productivity p "
        "JOIN author a ON a.author_id = p.author_id ORDER BY p.paper_count DESC LIMIT :limit"
    ),
    "author_paper_count": (
        "SELECT a.name, COUNT(*) AS papers FROM author a JOIN authorship au ON au.author_id = a.author_id "
        "WHERE a.name ILIKE :author_name GROUP BY a.name"
    ),
    "author_coauthors": (
        "SELECT a2.name, ce.weight FROM author a1 "
        "JOIN coauthor_edge ce ON ce.src = a1.author_id OR ce.dst = a1.author_id "
        "JOIN author a2 ON a2.author_id = CASE WHEN ce.src = a1.author_id THEN ce.dst ELSE ce.src END "
        "WHERE a1.name ILIKE :author_name ORDER BY ce.weight DESC LIMIT :limit"
    ),
    "papers_in_venue_year": (
        "SELECT COUNT(*) AS papers FROM paper p JOIN venue v ON v.venue_id = p.venue_id "
        "WHERE v.key_prefix = :venue AND p.year = CAST(:year AS SMALLINT)"
    ),
    "author_pagerank": (
        "SELECT a.name, am.pagerank, am.pagerank_percentile FROM author a "
        "JOIN author_metrics am ON am.author_id = a.author_id WHERE a.name ILIKE :author_name"
    ),
    "author_betweenness": (
        "SELECT a.name, am.betweenness, am.betweenness_percentile FROM author a "
        "JOIN author_metrics am ON am.author_id = a.author_id WHERE a.name ILIKE :author_name"
    ),
    "top_pagerank": (
        "SELECT a.name, am.pagerank FROM author_metrics am JOIN author a ON a.author_id = am.author_id "
        "ORDER BY am.pagerank DESC LIMIT :limit"
    ),
    "top_betweenness": (
        "SELECT a.name, am.betweenness FROM author_metrics am JOIN author a ON a.author_id = am.author_id "
        "ORDER BY am.betweenness DESC LIMIT :limit"
    ),
    "team_size_by_year": (
        "SELECT year, median_team_size, p25_team_size, p75_team_size FROM v_team_size_by_year "
        "WHERE year = CAST(:year AS SMALLINT)"
    ),
    "venue_type_breakdown": (
        "SELECT type, COUNT(*) AS papers FROM paper p JOIN venue v ON v.venue_id = p.venue_id GROUP BY type"
    ),
    "author_papers_list": (
        "SELECT p.dblp_key, p.title, p.year FROM paper p JOIN authorship au ON au.paper_id = p.paper_id "
        "JOIN author a ON a.author_id = au.author_id WHERE a.name ILIKE :author_name "
        "ORDER BY p.year DESC LIMIT :limit"
    ),
    "citation_count": (
        "SELECT p.dblp_key, COUNT(c.citing_id) AS cited_by_count FROM paper p "
        "LEFT JOIN citation c ON c.cited_id = p.paper_id WHERE p.dblp_key = :dblp_key GROUP BY p.dblp_key"
    ),
    "paper_lookup": "SELECT dblp_key, title, year, abstract FROM paper WHERE dblp_key = :dblp_key",
}

_TEMPLATE_DEFAULTS = {"limit": 10, "year_from": None, "year_to": None}


class UnknownTemplate(ValueError):
    pass


def sql_query(template: str, params: dict | None = None) -> list[dict]:
    if template not in SQL_TEMPLATES:
        raise UnknownTemplate(f"unknown template: {template}. Known: {sorted(SQL_TEMPLATES)}")
    if ReadOnlySession is None:
        raise RuntimeError("DATABASE_URL_READONLY is not configured")

    bind_params = {**_TEMPLATE_DEFAULTS, **(params or {})}
    with ReadOnlySession() as session:
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        rows = session.execute(text(SQL_TEMPLATES[template]), bind_params).mappings().all()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# semantic_search
# ---------------------------------------------------------------------------

def embed_query(text_query: str) -> list[float]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{OLLAMA_URL}/api/embed", json={"model": EMBED_MODEL, "input": [text_query]})
        resp.raise_for_status()
        return resp.json()["embeddings"][0]


def semantic_search(query: str, year_from: int | None = None, venue: str | None = None) -> list[dict]:
    vector = embed_query(query)
    vector_literal = "[" + ",".join(f"{x:.6f}" for x in vector) + "]"

    with ReadOnlySession() as session:
        session.execute(text("SET LOCAL statement_timeout = '5s'"))
        rows = session.execute(
            text("""
                SELECT p.dblp_key, p.title, p.year, v.key_prefix,
                       1 - (pe.embedding <=> CAST(:vector AS vector)) AS similarity
                FROM paper_embedding pe
                JOIN paper p ON p.paper_id = pe.paper_id
                LEFT JOIN venue v ON v.venue_id = p.venue_id
                WHERE (CAST(:year_from AS SMALLINT) IS NULL OR p.year >= CAST(:year_from AS SMALLINT))
                  AND (CAST(:venue AS TEXT) IS NULL OR v.key_prefix = CAST(:venue AS TEXT))
                ORDER BY pe.embedding <=> CAST(:vector AS vector)
                LIMIT 10
            """),
            {"vector": vector_literal, "year_from": year_from, "venue": venue},
        ).mappings().all()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# graph_query
# ---------------------------------------------------------------------------

def _get_adjacency(session: Session) -> dict[int, set[int]]:
    from app.routers.graph import get_adjacency
    return get_adjacency(session)


def graph_query(kind: str, params: dict) -> dict:
    if ReadOnlySession is None:
        raise RuntimeError("DATABASE_URL_READONLY is not configured")

    def _pick(*keys: str) -> str | None:
        for key in keys:
            if params.get(key):
                return params[key]
        return None

    with ReadOnlySession() as session:
        if kind == "shortest_path":
            a_name = _pick("author_a", "author1", "from", "source", "a")
            b_name = _pick("author_b", "author2", "to", "target", "b")
            if not a_name or not b_name:
                return {"error": "shortest_path needs author_a and author_b"}
            a_row = session.execute(text("SELECT author_id, name FROM author WHERE name ILIKE :n LIMIT 1"), {"n": a_name}).first()
            b_row = session.execute(text("SELECT author_id, name FROM author WHERE name ILIKE :n LIMIT 1"), {"n": b_name}).first()
            if not a_row or not b_row:
                return {"error": "author not found"}
            adjacency = _get_adjacency(session)
            path = _bfs(adjacency, a_row[0], b_row[0], max_hops=3)
            if path is None:
                return {"path": None}
            names = session.execute(text("SELECT author_id, name FROM author WHERE author_id = ANY(:ids)"), {"ids": path}).all()
            name_map = dict(names)
            return {"path": [{"author_id": n, "name": name_map.get(n)} for n in path]}

        if kind == "ego_network":
            author_name = _pick("author_name", "author", "name")
            if not author_name:
                return {"error": "ego_network needs author_name"}
            row = session.execute(text("SELECT author_id FROM author WHERE name ILIKE :n LIMIT 1"), {"n": author_name}).first()
            if not row:
                return {"error": "author not found"}
            adjacency = _get_adjacency(session)
            neighbors = list(adjacency.get(row[0], set()))[:20]
            names = session.execute(text("SELECT author_id, name FROM author WHERE author_id = ANY(:ids)"), {"ids": neighbors}).all()
            return {"neighbors": [{"author_id": n, "name": name} for n, name in names]}

        return {"error": f"unknown graph_query kind: {kind}"}


def _bfs(adjacency: dict[int, set[int]], a: int, b: int, max_hops: int) -> list[int] | None:
    if a == b:
        return [a]
    from collections import deque
    parent = {a: a}
    depth = {a: 0}
    queue = deque([a])
    while queue:
        current = queue.popleft()
        if depth[current] >= max_hops:
            continue
        for neighbor in adjacency.get(current, set()):
            if neighbor not in parent:
                parent[neighbor] = current
                depth[neighbor] = depth[current] + 1
                if neighbor == b:
                    path = [b]
                    while path[-1] != a:
                        path.append(parent[path[-1]])
                    path.reverse()
                    return path
                queue.append(neighbor)
    return None


# ---------------------------------------------------------------------------
# JSON schemas for Ollama's OpenAI-compatible tool-calling (§6.4/CHAT-2)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "Embeds the query and returns the top-10 papers by cosine similarity, with optional filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "year_from": {"type": "integer"},
                    "venue": {"type": "string", "description": "dblp venue key prefix, e.g. conf/kdd"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sql_query",
            "description": f"Runs one of these fixed SQL templates: {', '.join(sorted(SQL_TEMPLATES))}.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template": {"type": "string", "enum": sorted(SQL_TEMPLATES)},
                    "params": {"type": "object", "description": "template parameters, e.g. {\"author_name\": \"%Bengio%\", \"limit\": 10}"},
                },
                "required": ["template"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "graph_query",
            "description": (
                "Reads author_metrics and runs shortest-path or ego-network queries "
                "(read-only, max 3 hops). For kind=shortest_path, params must be exactly "
                '{"author_a": "<name>", "author_b": "<name>"}. For kind=ego_network, params '
                'must be exactly {"author_name": "<name>"}.'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["shortest_path", "ego_network"]},
                    "params": {
                        "type": "object",
                        "properties": {
                            "author_a": {"type": "string", "description": "shortest_path only"},
                            "author_b": {"type": "string", "description": "shortest_path only"},
                            "author_name": {"type": "string", "description": "ego_network only"},
                        },
                    },
                },
                "required": ["kind", "params"],
            },
        },
    },
]


def call_tool(name: str, arguments: dict) -> dict | list:
    if name == "semantic_search":
        return semantic_search(**arguments)
    if name == "sql_query":
        return sql_query(arguments["template"], arguments.get("params"))
    if name == "graph_query":
        return graph_query(arguments["kind"], arguments.get("params", {}))
    raise ValueError(f"unknown tool: {name}")
