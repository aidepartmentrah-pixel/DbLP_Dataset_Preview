"""P3 / DB-3: enrich papers with abstracts and citation edges from the real
OpenAlex API, by DOI, 50 at a time.

Real finding (not assumed from the proposal text): OpenAlex's live API
returns `X-RateLimit-Limit: 1000` / `X-RateLimit-Reset: <seconds>` headers
per request - a credit budget (1 request = 1 credit, regardless of how many
DOIs are batched into that request's filter) over a multi-hour window, not
the unlimited/simple-throttle "polite pool" the proposal's text assumed.
With 229,584 papers needing 50-DOI batches, a full enrichment needs ~4,592
requests - about 4.6x a single window's budget. So this job is designed to
be safely resumable across multiple runs/windows instead of a one-shot full
pass:
  - Only processes papers where `abstract IS NULL` (so a later run picks up
    exactly where an earlier, credit-limited run left off).
  - Reads the real `X-RateLimit-Remaining` header after every request and
    stops gracefully, mid-job, well before it would trip the limit - never
    just hopes a fixed request count is safe.
  - Writes are additive (`UPDATE ... WHERE abstract IS NULL`, `INSERT ...
    ON CONFLICT DO NOTHING`), not a truncate-and-swap, since later runs are
    expected to extend a previous one, not replace it.

Citation edges can only be discovered between two papers this job has
*both* actually fetched (a referenced work is identified by an opaque
OpenAlex id, not a DOI, so there is no way to know it's "one of ours"
without having already looked it up) - so citation coverage grows honestly
alongside abstract coverage across runs, rather than pretending to be
complete after a single partial pass.

Run inside the `jobs` container, e.g.:
    python enrich_openalex.py
"""

from __future__ import annotations

import os
import time

import httpx
import psycopg

BATCH_SIZE = 50
DEFAULT_SAFETY_MARGIN = 20  # stop once X-RateLimit-Remaining drops to this
DEFAULT_MAX_REQUESTS = 900  # hard cap regardless of what headers report


def invert_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as {word: [positions]} to avoid copyright
    issues with redistributing raw text. Rebuild the original word order."""
    if not inverted_index:
        return None
    positions: dict[int, str] = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    if not positions:
        return None
    return " ".join(positions[i] for i in sorted(positions))


def strip_doi_prefix(doi_url: str | None) -> str | None:
    if not doi_url:
        return None
    for prefix in ("https://doi.org/", "http://doi.org/"):
        if doi_url.startswith(prefix):
            return doi_url[len(prefix):]
    return doi_url


def parse_work(work: dict) -> dict:
    return {
        "openalex_id": work.get("id"),
        "doi": strip_doi_prefix(work.get("doi")),
        "abstract": invert_abstract(work.get("abstract_inverted_index")),
        "referenced_works": work.get("referenced_works") or [],
    }


class RateLimitStop(Exception):
    """Raised to end the run early and cleanly once the live rate-limit
    headers say we're close to the budget - not an error, just a stop."""


def fetch_batch(client: httpx.Client, dois: list[str], mailto: str, safety_margin: int) -> list[dict]:
    filter_value = "|".join(dois)
    resp = client.get(
        "https://api.openalex.org/works",
        params={"filter": f"doi:{filter_value}", "mailto": mailto, "per-page": len(dois)},
    )
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", "5"))
        time.sleep(retry_after)
        resp = client.get(
            "https://api.openalex.org/works",
            params={"filter": f"doi:{filter_value}", "mailto": mailto, "per-page": len(dois)},
        )
    resp.raise_for_status()

    remaining = resp.headers.get("X-RateLimit-Remaining")
    if remaining is not None and int(remaining) <= safety_margin:
        raise RateLimitStop(f"X-RateLimit-Remaining={remaining} <= safety margin {safety_margin}")

    return resp.json().get("results", [])


def run_enrichment(
    database_url: str,
    mailto: str,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    safety_margin: int = DEFAULT_SAFETY_MARGIN,
) -> dict:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT paper_id, doi FROM paper WHERE doi IS NOT NULL AND abstract IS NULL")
            pending = cur.fetchall()

    print(f"[enrich] {len(pending):,} papers with a DOI still need enrichment", flush=True)

    doi_to_paper_id = {doi: paper_id for paper_id, doi in pending}
    openalex_id_to_paper_id: dict[str, int] = {}
    abstracts: dict[int, str] = {}
    referenced_by: dict[int, list[str]] = {}

    requests_made = 0
    stopped_reason = "exhausted all pending papers"

    with httpx.Client(timeout=30.0) as client:
        for start in range(0, len(pending), BATCH_SIZE):
            if requests_made >= max_requests:
                stopped_reason = f"reached max_requests={max_requests}"
                break
            batch = pending[start:start + BATCH_SIZE]
            dois = [doi for _pid, doi in batch]
            try:
                results = fetch_batch(client, dois, mailto, safety_margin)
            except RateLimitStop as e:
                stopped_reason = str(e)
                break
            requests_made += 1

            for work in results:
                parsed = parse_work(work)
                paper_id = doi_to_paper_id.get(parsed["doi"])
                if paper_id is None or not parsed["openalex_id"]:
                    continue
                openalex_id_to_paper_id[parsed["openalex_id"]] = paper_id
                if parsed["abstract"]:
                    abstracts[paper_id] = parsed["abstract"]
                referenced_by[paper_id] = parsed["referenced_works"]

            if requests_made % 20 == 0:
                print(f"[enrich] {requests_made} requests, {len(abstracts):,} abstracts so far", flush=True)

    citation_edges = [
        (citing_id, openalex_id_to_paper_id[ref])
        for citing_id, refs in referenced_by.items()
        for ref in refs
        if ref in openalex_id_to_paper_id
    ]

    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            for paper_id, abstract in abstracts.items():
                cur.execute(
                    "UPDATE paper SET abstract = %s WHERE paper_id = %s AND abstract IS NULL",
                    (abstract, paper_id),
                )
            for citing_id, cited_id in citation_edges:
                cur.execute(
                    "INSERT INTO citation (citing_id, cited_id) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING",
                    (citing_id, cited_id),
                )
        conn.commit()

    print(f"[enrich] stopped: {stopped_reason}", flush=True)
    return {
        "requests_made": requests_made,
        "papers_checked": min(requests_made * BATCH_SIZE, len(pending)),
        "abstracts_written": len(abstracts),
        "citation_edges_written": len(citation_edges),
        "stopped_reason": stopped_reason,
    }


def main():
    database_url = os.environ["DATABASE_URL"]
    mailto = os.environ.get("OPENALEX_MAILTO", "")
    if not mailto:
        raise SystemExit("OPENALEX_MAILTO is required (a polite pool needs a real contact email)")

    max_requests = int(os.environ.get("OPENALEX_MAX_REQUESTS", DEFAULT_MAX_REQUESTS))
    counts = run_enrichment(database_url, mailto, max_requests=max_requests)
    print(
        f"Made {counts['requests_made']:,} requests, wrote {counts['abstracts_written']:,} abstracts "
        f"and {counts['citation_edges_written']:,} citation edges ({counts['stopped_reason']})"
    )


if __name__ == "__main__":
    main()
