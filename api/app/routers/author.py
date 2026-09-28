from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

router = APIRouter(prefix="/api/author", tags=["author"])


@router.get("/{author_id}")
def author_profile(author_id: int, session: Session = Depends(get_session)):
    row = session.execute(
        text("""
            SELECT a.author_id, a.name, a.orcid, am.pagerank, am.betweenness,
                   am.pagerank_percentile, am.betweenness_percentile, am.degree, am.community
            FROM author a
            LEFT JOIN author_metrics am ON am.author_id = a.author_id
            WHERE a.author_id = :id
        """),
        {"id": author_id},
    ).mappings().first()
    if row is None:
        raise HTTPException(404, "author not found")

    papers = session.execute(
        text("""
            SELECT p.dblp_key, p.title, p.year, v.key_prefix, v.type
            FROM authorship au
            JOIN paper p ON p.paper_id = au.paper_id
            LEFT JOIN venue v ON v.venue_id = p.venue_id
            WHERE au.author_id = :id
            ORDER BY p.year DESC
        """),
        {"id": author_id},
    ).all()

    coauthors = session.execute(
        text("""
            SELECT a2.author_id, a2.name, ce.weight
            FROM coauthor_edge ce
            JOIN author a2 ON a2.author_id = CASE WHEN ce.src = :id THEN ce.dst ELSE ce.src END
            WHERE ce.src = :id OR ce.dst = :id
            ORDER BY ce.weight DESC
            LIMIT 20
        """),
        {"id": author_id},
    ).all()

    return {
        "author_id": row["author_id"],
        "name": row["name"],
        "orcid": row["orcid"],
        "pagerank": row["pagerank"],
        "betweenness": row["betweenness"],
        "pagerank_percentile": row["pagerank_percentile"],
        "betweenness_percentile": row["betweenness_percentile"],
        "degree": row["degree"],
        "community": row["community"],
        "paper_count": len(papers),
        "papers": [
            {"dblp_key": r[0], "title": r[1], "year": r[2], "venue": r[3], "venue_type": r[4]}
            for r in papers
        ],
        "coauthors": [{"author_id": r[0], "name": r[1], "weight": r[2]} for r in coauthors],
    }
