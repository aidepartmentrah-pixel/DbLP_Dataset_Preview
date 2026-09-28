from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/rankings")
def rankings(
    sort: str = Query("pagerank", pattern="^(pagerank|betweenness)$"),
    limit: int = Query(50, ge=1, le=200),
    venue: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
    session: Session = Depends(get_session),
):
    sort_col = "am.pagerank" if sort == "pagerank" else "am.betweenness"
    no_filters = venue is None and year_from is None and year_to is None
    rows = session.execute(
        text(f"""
            SELECT am.author_id, a.name, am.pagerank, am.betweenness, am.degree,
                   am.community, am.pagerank_percentile, am.betweenness_percentile
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
            ORDER BY {sort_col} DESC
            LIMIT :limit
        """),
        {"no_filters": no_filters, "venue": venue, "year_from": year_from, "year_to": year_to, "limit": limit},
    ).all()
    return [
        {
            "author_id": r[0], "name": r[1], "pagerank": r[2], "betweenness": r[3],
            "degree": r[4], "community": r[5],
            "pagerank_percentile": r[6], "betweenness_percentile": r[7],
        }
        for r in rows
    ]


@router.get("/scatter")
def scatter(limit: int = Query(2000, ge=1, le=10000), session: Session = Depends(get_session)):
    rows = session.execute(
        text("""
            SELECT am.author_id, a.name, am.pagerank_percentile, am.betweenness_percentile
            FROM author_metrics am
            JOIN author a ON a.author_id = am.author_id
            ORDER BY am.pagerank_percentile DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).all()
    return [
        {"author_id": r[0], "name": r[1], "pagerank_percentile": r[2], "betweenness_percentile": r[3]}
        for r in rows
    ]
