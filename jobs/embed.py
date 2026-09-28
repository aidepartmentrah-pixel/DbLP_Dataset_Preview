"""P7 / CHAT-1: one text chunk per paper -> nomic-embed-text (via Ollama,
batches of 64) -> paper_embedding (pgvector).

Chunk = title + venue + year + authors + abstract (§6.3); the abstract only
exists for papers P3 has enriched so far (see "2. Initial Slicing Task
Table.md", P3's real, honest coverage note) - the title-based fields alone
are the fallback for the rest, exactly as the proposal specifies.

Run inside the `jobs` container, e.g.:
    python embed.py
"""

from __future__ import annotations

import os
import time

import httpx
import psycopg

BATCH_SIZE = 64
EMBED_DIM = 768


def build_chunk(title: str, venue_prefix: str | None, year: int | None, authors: list[str], abstract: str | None) -> str:
    parts = [title]
    if venue_prefix:
        parts.append(venue_prefix)
    if year:
        parts.append(str(year))
    if authors:
        parts.append(", ".join(a for a in authors if a))
    if abstract:
        parts.append(abstract)
    return " | ".join(parts)


def fetch_pending(cur, limit: int | None) -> list[tuple[int, str]]:
    cur.execute("""
        SELECT p.paper_id, p.title, v.key_prefix, p.year, p.abstract,
               array_agg(a.name ORDER BY au."position") FILTER (WHERE a.name IS NOT NULL) AS authors
        FROM paper p
        LEFT JOIN venue v ON v.venue_id = p.venue_id
        LEFT JOIN authorship au ON au.paper_id = p.paper_id
        LEFT JOIN author a ON a.author_id = au.author_id
        LEFT JOIN paper_embedding pe ON pe.paper_id = p.paper_id
        WHERE pe.paper_id IS NULL
        GROUP BY p.paper_id, p.title, v.key_prefix, p.year, p.abstract
        ORDER BY p.paper_id
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    return [
        (paper_id, build_chunk(title, venue_prefix, year, authors or [], abstract))
        for paper_id, title, venue_prefix, year, abstract, authors in rows
    ]


def embed_batch(client: httpx.Client, ollama_url: str, model: str, texts: list[str]) -> list[list[float]]:
    resp = client.post(f"{ollama_url}/api/embed", json={"model": model, "input": texts})
    resp.raise_for_status()
    return resp.json()["embeddings"]


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


def run_embedding(database_url: str, ollama_url: str, model: str, limit: int | None = None) -> dict:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            pending = fetch_pending(cur, limit)

    print(f"[embed] {len(pending):,} papers still need an embedding", flush=True)
    if not pending:
        return {"embedded": 0}

    embedded = 0
    with httpx.Client(timeout=60.0) as client, psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            for start in range(0, len(pending), BATCH_SIZE):
                batch = pending[start:start + BATCH_SIZE]
                vectors = embed_batch(client, ollama_url, model, [text for _pid, text in batch])
                for (paper_id, _text), vec in zip(batch, vectors):
                    cur.execute(
                        "INSERT INTO paper_embedding (paper_id, embedding) VALUES (%s, %s) "
                        "ON CONFLICT (paper_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                        (paper_id, _vector_literal(vec)),
                    )
                embedded += len(batch)
                if embedded % (BATCH_SIZE * 10) == 0:
                    conn.commit()
                    print(f"[embed] {embedded:,}/{len(pending):,} embedded", flush=True)
        conn.commit()

    return {"embedded": embedded}


def main():
    database_url = os.environ["DATABASE_URL"]
    ollama_url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
    model = os.environ.get("EMBED_MODEL", "nomic-embed-text")
    limit = int(os.environ["EMBED_LIMIT"]) if os.environ.get("EMBED_LIMIT") else None

    t0 = time.time()
    counts = run_embedding(database_url, ollama_url, model, limit)
    print(f"Embedded {counts['embedded']:,} papers in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
