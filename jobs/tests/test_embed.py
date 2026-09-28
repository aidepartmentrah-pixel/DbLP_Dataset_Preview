"""CHAT-1 accept check: the chunk-building logic (title + venue + year +
authors + abstract, title-only fallback)."""

from embed import build_chunk


def test_build_chunk_full():
    chunk = build_chunk("Graph Learning", "conf/kdd", 2021, ["Jane Smith", "Wei Wang"], "We study graphs.")
    assert chunk == "Graph Learning | conf/kdd | 2021 | Jane Smith, Wei Wang | We study graphs."


def test_build_chunk_falls_back_to_title_when_nothing_else_present():
    assert build_chunk("Graph Learning", None, None, [], None) == "Graph Learning"


def test_build_chunk_without_abstract():
    chunk = build_chunk("Graph Learning", "conf/kdd", 2021, ["Jane Smith"], None)
    assert chunk == "Graph Learning | conf/kdd | 2021 | Jane Smith"
