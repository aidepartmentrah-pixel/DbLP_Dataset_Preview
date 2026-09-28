"""DB-3 accept check: mocked-OpenAlex-response tests, plus a rate-limit/
backoff test - no real network calls here (the real live-API run is a
separate, manual step; see "2. Initial Slicing Task Table.md", P3)."""

import httpx
import pytest

from enrich_openalex import RateLimitStop, fetch_batch, invert_abstract, parse_work, strip_doi_prefix


def test_invert_abstract_rebuilds_word_order():
    # "cats love dogs" scrambled into OpenAlex's {word: [positions]} form.
    inverted = {"love": [1], "cats": [0], "dogs": [2]}
    assert invert_abstract(inverted) == "cats love dogs"


def test_invert_abstract_repeated_word():
    inverted = {"the": [0, 3], "cat": [1], "chased": [2], "cat's": [4], "tail": [5]}
    assert invert_abstract(inverted) == "the cat chased the cat's tail"


def test_invert_abstract_none_or_empty():
    assert invert_abstract(None) is None
    assert invert_abstract({}) is None


def test_strip_doi_prefix():
    assert strip_doi_prefix("https://doi.org/10.1/abc") == "10.1/abc"
    assert strip_doi_prefix("http://doi.org/10.1/abc") == "10.1/abc"
    assert strip_doi_prefix(None) is None


def test_parse_work_extracts_fields():
    work = {
        "id": "https://openalex.org/W123",
        "doi": "https://doi.org/10.1/abc",
        "abstract_inverted_index": {"hello": [0], "world": [1]},
        "referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"],
    }
    parsed = parse_work(work)
    assert parsed == {
        "openalex_id": "https://openalex.org/W123",
        "doi": "10.1/abc",
        "abstract": "hello world",
        "referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"],
    }


def test_fetch_batch_stops_when_rate_limit_low():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": []}, headers={"X-RateLimit-Remaining": "5"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RateLimitStop):
        fetch_batch(client, ["10.1/a"], "me@example.com", safety_margin=20)


def test_fetch_batch_continues_when_rate_limit_healthy():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/a"}]},
            headers={"X-RateLimit-Remaining": "500"},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = fetch_batch(client, ["10.1/a"], "me@example.com", safety_margin=20)
    assert len(results) == 1
    assert results[0]["doi"] == "https://doi.org/10.1/a"


def test_fetch_batch_retries_once_after_429():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"results": []}, headers={"X-RateLimit-Remaining": "500"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = fetch_batch(client, ["10.1/a"], "me@example.com", safety_margin=20)
    assert results == []
    assert len(calls) == 2
