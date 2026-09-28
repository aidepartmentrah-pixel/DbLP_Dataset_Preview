from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/kpis")
def kpis(session: Session = Depends(get_session)):
    row = session.execute(text("SELECT * FROM v_kpis")).mappings().one()
    return {
        "papers": row["paper_count"],
        "authors": row["author_count"],
        "venues": row["venue_count"],
        "last_update": row["last_update"],
    }


@router.get("/papers-per-year")
def papers_per_year(session: Session = Depends(get_session)):
    rows = session.execute(
        text("SELECT year, series, paper_count FROM v_papers_per_year ORDER BY year")
    ).all()
    by_year: dict[int, dict] = {}
    for year, series, count in rows:
        by_year.setdefault(year, {"year": year, "journal": 0, "conference": 0, "other": 0})
        by_year[year][series] = count
    return sorted(by_year.values(), key=lambda r: r["year"])


@router.get("/top-venues")
def top_venues(
    limit: int = Query(15, ge=1, le=100),
    year_from: int | None = None,
    year_to: int | None = None,
    session: Session = Depends(get_session),
):
    rows = session.execute(
        text("""
            SELECT key_prefix, name, type, SUM(paper_count) AS paper_count
            FROM v_top_venues
            WHERE (CAST(:year_from AS SMALLINT) IS NULL OR year >= CAST(:year_from AS SMALLINT))
              AND (CAST(:year_to AS SMALLINT) IS NULL OR year <= CAST(:year_to AS SMALLINT))
            GROUP BY key_prefix, name, type
            ORDER BY paper_count DESC
            LIMIT :limit
        """),
        {"limit": limit, "year_from": year_from, "year_to": year_to},
    ).all()
    return [
        {"venue": prefix, "name": name, "type": type_, "paper_count": count}
        for prefix, name, type_, count in rows
    ]


@router.get("/top-authors")
def top_authors(limit: int = Query(15, ge=1, le=100), session: Session = Depends(get_session)):
    rows = session.execute(
        text("""
            SELECT a.author_id, a.name, p.paper_count
            FROM v_author_productivity p
            JOIN author a ON a.author_id = p.author_id
            ORDER BY p.paper_count DESC
            LIMIT :limit
        """),
        {"limit": limit},
    ).all()
    return [
        {"author_id": author_id, "name": name, "paper_count": count}
        for author_id, name, count in rows
    ]


@router.get("/team-size")
def team_size(session: Session = Depends(get_session)):
    rows = session.execute(
        text("""
            SELECT year, paper_count, median_team_size, p25_team_size, p75_team_size
            FROM v_team_size_by_year
            ORDER BY year
        """)
    ).all()
    return [
        {
            "year": year,
            "paper_count": paper_count,
            "median": median,
            "p25": p25,
            "p75": p75,
        }
        for year, paper_count, median, p25, p75 in rows
    ]


@router.get("/productivity")
def productivity(session: Session = Depends(get_session)):
    rows = session.execute(
        text("""
            SELECT paper_count, COUNT(*) AS num_authors
            FROM v_author_productivity
            GROUP BY paper_count
            ORDER BY paper_count
        """)
    ).all()
    return [{"papers": papers, "authors": authors} for papers, authors in rows]


@router.get("/topic-trends")
def topic_trends(session: Session = Depends(get_session)):
    rows = session.execute(
        text("SELECT word, year, paper_count FROM topic_year_counts ORDER BY word, year")
    ).all()
    return [{"word": word, "year": year, "paper_count": count} for word, year, count in rows]
