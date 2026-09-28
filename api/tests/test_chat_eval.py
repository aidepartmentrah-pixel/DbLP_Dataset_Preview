"""CHAT-7: runs api/tests/chat_eval.jsonl against the real live stack (real
Postgres, real Ollama/qwen3:8b) - not mocked, per this project's standing
preference for real proof. Run with: pytest -m eval

Each question already carries a real, DB-verified expected fact (see
generate_chat_eval.py) - grading here is a simple, auto-checkable proxy per
category, not full semantic correctness judging, but every citation the
model returns is independently re-validated against the real `paper` table
for the accept criterion (0 invented dblp keys reach the user).
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

EVAL_FILE = Path(__file__).parent / "chat_eval.jsonl"


def _load_questions() -> list[dict]:
    if not EVAL_FILE.exists():
        return []
    return [json.loads(line) for line in EVAL_FILE.read_text().splitlines() if line.strip()]


def _ask(client: TestClient, question: str) -> tuple[str, list[str]]:
    with client.stream("POST", "/api/chat", json={"message": question}) as resp:
        text_parts = []
        citations: list[str] = []
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: "):])
            if event["type"] == "token":
                text_parts.append(event["content"])
            elif event["type"] == "done":
                citations = event["citations"]
    return "".join(text_parts), citations


def _grade(q: dict, answer: str, citations: list[str]) -> bool:
    if q["category"] == "factual":
        # Real finding from the live eval run: qwen3:8b reliably gets the
        # right number (verified by manually re-checking several "failures"
        # against the real DB) but often writes it with a thousands
        # separator ("334,137"), which a strict substring match against the
        # unformatted DB value ("334137") doesn't catch. This is a grading
        # bug, not a model or retrieval bug, so strip commas from both sides.
        return q["expected_contains"].replace(",", "") in answer.replace(",", "")
    if q["category"] == "topical":
        return len(citations) > 0
    if q["category"] == "graph":
        if q.get("expected_contains") == "yes_coauthors":
            return "yes" in answer.lower() or "co-author" in answer.lower()
        if "expected_contains" in q:
            return q["expected_contains"] in answer
        return len(answer.strip()) > 0
    return False


@pytest.mark.eval
@pytest.mark.parametrize("q", _load_questions(), ids=lambda q: q["question"][:60])
def test_chat_eval_question(q):
    with TestClient(app) as client:
        answer, citations = _ask(client, q["question"])
    # Every citation must be a real, DB-verified dblp key (CHAT-6) - the
    # chat endpoint itself already filters these, so this is a second,
    # independent check that nothing slipped through.
    from app.db import SessionLocal
    from sqlalchemy import text as sql_text

    if citations:
        with SessionLocal() as session:
            rows = session.execute(
                sql_text("SELECT dblp_key FROM paper WHERE dblp_key = ANY(:keys)"),
                {"keys": citations},
            ).all()
        assert {r[0] for r in rows} == set(citations), "a hallucinated key reached the eval result"

    assert _grade(q, answer, citations), f"answer did not satisfy grading: {answer!r}"
