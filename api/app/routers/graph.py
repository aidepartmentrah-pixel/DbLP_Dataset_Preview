from collections import Counter, deque

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("/search-author")
def search_author(q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)):
    """Backs GRAPH-2's search box and the GRAPH-3 author pickers."""
    rows = session.execute(
        text("""
            SELECT a.author_id, a.name, COALESCE(am.pagerank, 0) AS pagerank
            FROM author a
            LEFT JOIN author_metrics am ON am.author_id = a.author_id
            WHERE a.name ILIKE '%' || :q || '%'
            ORDER BY pagerank DESC
            LIMIT :limit
        """),
        {"q": q, "limit": limit},
    ).all()
    return [{"author_id": r[0], "name": r[1]} for r in rows]

# Real bug found testing GRAPH-3 against actual high-degree authors (not the
# small seeded test DB): a naive BFS issuing one SQL query per visited node
# took 62.8s for a real path (Philip S. Yu -> Yoshua Bengio, both very
# high-degree). Fixed by loading the whole coauthor_edge adjacency into
# memory once and doing BFS/ego traversal on that in-memory, instead of
# round-tripping to Postgres for every node touched.
#
# Second real bug, found immediately after by the test suite itself: caching
# this forever per-process is actually wrong, not just in tests (each test
# points at a fresh, differently-seeded database, so a first-test cache was
# silently served to later tests) but in production too - a later ETL/
# centrality re-run would refresh `coauthor_edge` while the API process kept
# running, and every graph query would keep serving stale data until a
# manual restart. Fixed by keying the cache on `etl_meta.loaded_at`, which
# both P2 and the test fixtures already bump on every real data load, so it
# invalidates correctly in both cases without any extra bookkeeping table.
_adjacency_cache: tuple[object, dict[int, set[int]]] | None = None


def get_adjacency(session: Session) -> dict[int, set[int]]:
    global _adjacency_cache
    current_key = session.execute(text("SELECT loaded_at FROM etl_meta WHERE id = 1")).scalar()
    if _adjacency_cache is None or _adjacency_cache[0] != current_key:
        rows = session.execute(text("SELECT src, dst FROM coauthor_edge")).all()
        adjacency: dict[int, set[int]] = {}
        for src, dst in rows:
            adjacency.setdefault(src, set()).add(dst)
            adjacency.setdefault(dst, set()).add(src)
        _adjacency_cache = (current_key, adjacency)
    return _adjacency_cache[1]

_SELECT_AUTHORS_FILTERED = """
    SELECT am.author_id, a.name, am.pagerank, am.betweenness, am.community, am.degree
    FROM author_metrics am
    JOIN author a ON a.author_id = am.author_id
    WHERE :no_filters OR EXISTS (
        SELECT 1 FROM authorship au
        JOIN paper p ON p.paper_id = au.paper_id
        JOIN venue v ON v.venue_id = p.venue_id
        WHERE au.author_id = am.author_id
          AND (CAST(:venue AS TEXT) IS NULL OR v.key_prefix = CAST(:venue AS TEXT))
          AND (CAST(:year_from AS SMALLINT) IS NULL OR p.year >= CAST(:year_from AS SMALLINT))
          AND (CAST(:year_to AS SMALLINT) IS NULL OR p.year <= CAST(:year_to AS SMALLINT))
    )
    ORDER BY am.pagerank DESC
    LIMIT :top
"""


def _filter_params(venue: str | None, year_from: int | None, year_to: int | None, top: int) -> dict:
    return {
        "no_filters": venue is None and year_from is None and year_to is None,
        "venue": venue, "year_from": year_from, "year_to": year_to, "top": top,
    }


@router.get("/coauthors")
def coauthors(
    venue: str | None = None,
    year_from: int | None = Query(None, alias="from"),
    year_to: int | None = Query(None, alias="to"),
    top: int = Query(500, ge=1, le=2000),
    session: Session = Depends(get_session),
):
    authors = session.execute(
        text(_SELECT_AUTHORS_FILTERED), _filter_params(venue, year_from, year_to, top)
    ).all()
    ids = [row[0] for row in authors]
    if not ids:
        return {"nodes": [], "edges": []}

    edges = session.execute(
        text("""
            SELECT src, dst, weight, first_year, last_year
            FROM coauthor_edge
            WHERE src = ANY(:ids) AND dst = ANY(:ids)
        """),
        {"ids": ids},
    ).all()

    return {
        "nodes": [
            {
                "author_id": r[0], "name": r[1], "pagerank": r[2],
                "betweenness": r[3], "community": r[4], "degree": r[5],
            }
            for r in authors
        ],
        "edges": [
            {"src": r[0], "dst": r[1], "weight": r[2], "first_year": r[3], "last_year": r[4]}
            for r in edges
        ],
    }


@router.get("/ego/{author_id}")
def ego(author_id: int, hops: int = Query(1, ge=1, le=2), session: Session = Depends(get_session)):
    center = session.execute(
        text("SELECT author_id, name FROM author WHERE author_id = :id"), {"id": author_id}
    ).first()
    if center is None:
        raise HTTPException(404, "author not found")

    adjacency = get_adjacency(session)
    frontier = {author_id}
    visited = {author_id}
    for _ in range(hops):
        if not frontier:
            break
        next_frontier = set()
        for node in frontier:
            next_frontier |= adjacency.get(node, set()) - visited
        visited |= next_frontier
        frontier = next_frontier
        if len(visited) > 300:
            break

    ids = list(visited)[:300]
    authors = session.execute(
        text("""
            SELECT am.author_id, a.name, am.pagerank, am.betweenness, am.community, am.degree
            FROM author_metrics am JOIN author a ON a.author_id = am.author_id
            WHERE am.author_id = ANY(:ids)
        """),
        {"ids": ids},
    ).all()
    edges = session.execute(
        text("SELECT src, dst, weight, first_year, last_year FROM coauthor_edge WHERE src = ANY(:ids) AND dst = ANY(:ids)"),
        {"ids": ids},
    ).all()

    return {
        "center": {"author_id": center[0], "name": center[1]},
        "nodes": [
            {"author_id": r[0], "name": r[1], "pagerank": r[2], "betweenness": r[3], "community": r[4], "degree": r[5]}
            for r in authors
        ],
        "edges": [
            {"src": r[0], "dst": r[1], "weight": r[2], "first_year": r[3], "last_year": r[4]}
            for r in edges
        ],
    }


@router.get("/path")
def path(a: int, b: int, session: Session = Depends(get_session)):
    """BFS shortest path between two authors on coauthor_edge, max 6 hops."""
    if a == b:
        return {"path": [a], "hops": []}

    adjacency = get_adjacency(session)
    parent: dict[int, int] = {a: a}
    queue = deque([a])
    found = False
    depth = {a: 0}

    while queue and not found:
        current = queue.popleft()
        if depth[current] >= 6:
            continue
        for neighbor in adjacency.get(current, set()):
            if neighbor not in parent:
                parent[neighbor] = current
                depth[neighbor] = depth[current] + 1
                if neighbor == b:
                    found = True
                    break
                queue.append(neighbor)

    if not found:
        return {"path": None, "hops": []}

    node_path = [b]
    while node_path[-1] != a:
        node_path.append(parent[node_path[-1]])
    node_path.reverse()

    names = dict(session.execute(
        text("SELECT author_id, name FROM author WHERE author_id = ANY(:ids)"), {"ids": node_path}
    ).all())

    hops = []
    for u, v in zip(node_path, node_path[1:]):
        joint = session.execute(
            text("""
                SELECT p.dblp_key, p.title FROM authorship au1
                JOIN authorship au2 ON au1.paper_id = au2.paper_id
                JOIN paper p ON p.paper_id = au1.paper_id
                WHERE au1.author_id = :u AND au2.author_id = :v
                LIMIT 1
            """),
            {"u": u, "v": v},
        ).first()
        hops.append({
            "from": {"author_id": u, "name": names.get(u)},
            "to": {"author_id": v, "name": names.get(v)},
            "paper": {"dblp_key": joint[0], "title": joint[1]} if joint else None,
        })

    return {"path": [{"author_id": n, "name": names.get(n)} for n in node_path], "hops": hops}


@router.get("/communities")
def communities(
    venue: str | None = None,
    year_from: int | None = Query(None, alias="from"),
    year_to: int | None = Query(None, alias="to"),
    top: int = Query(500, ge=1, le=2000),
    session: Session = Depends(get_session),
):
    authors = session.execute(
        text(_SELECT_AUTHORS_FILTERED), _filter_params(venue, year_from, year_to, top)
    ).all()
    by_community: dict[int, list[int]] = {}
    for author_id, _name, _pr, _bw, community, _deg in authors:
        by_community.setdefault(community, []).append(author_id)

    top_communities = sorted(by_community.items(), key=lambda kv: len(kv[1]), reverse=True)[:6]

    result = []
    for community_id, author_ids in top_communities:
        titles = session.execute(
            text("""
                SELECT DISTINCT p.title FROM authorship au
                JOIN paper p ON p.paper_id = au.paper_id
                WHERE au.author_id = ANY(:ids)
                LIMIT 500
            """),
            {"ids": author_ids},
        ).all()
        words = Counter()
        for (title,) in titles:
            for word in title.lower().split():
                word = "".join(c for c in word if c.isalpha())
                if len(word) > 4:
                    words[word] += 1
        result.append({
            "community": community_id,
            "size": len(author_ids),
            "top_keywords": [w for w, _ in words.most_common(5)],
        })

    return result


@router.get("/degree-dist")
def degree_dist(session: Session = Depends(get_session)):
    rows = session.execute(
        text("SELECT degree, COUNT(*) AS num_authors FROM author_metrics GROUP BY degree ORDER BY degree")
    ).all()
    return [{"degree": r[0], "authors": r[1]} for r in rows]
