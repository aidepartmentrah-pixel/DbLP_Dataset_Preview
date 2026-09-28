"""CHAT-2..6: the RAG chatbot. An agent loop (capped at 4 tool calls, §6.4)
picks from three tools (chat_tools.py), then streams the final natural-
language answer over SSE, citing dblp keys that are validated against the
real database before being sent to the client (CHAT-6) - never trusting an
LLM-returned key without checking it.
"""

from __future__ import annotations

import json
import os
import re

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.chat_tools import TOOL_SCHEMAS, call_tool
from app.db import get_session

router = APIRouter(prefix="/api/chat", tags=["chat"])

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
MAX_TOOL_CALLS = 4
MAX_HISTORY_TURNS = 5

SYSTEM_PROMPT = (
    "You answer questions about the dblp computer science bibliography. "
    "Use the semantic_search, sql_query and graph_query tools to find real "
    "records before answering - never answer from memory. Cite every "
    "factual claim with the paper's [dblp_key] (e.g. [conf/kdd/SmithL21]) "
    "or the author's name, exactly as returned by a tool. If the tools "
    "find nothing relevant, say you could not find it - never invent a "
    "paper, author, or number."
)

CITATION_KEY_RE = re.compile(r"\[([a-zA-Z0-9/_.\-]+/[a-zA-Z0-9/_.\-]+)\]")

# Real, observed failure mode: qwen3:8b occasionally emits a tool call as
# literal `<tool_call>{"name": ..., "arguments": {...}}</tool_call>` text
# in `content` instead of the structured `tool_calls` field Ollama's
# OpenAI-compatible API expects - a known quirk of Qwen's own native
# chat-template convention leaking through. Treating an empty `tool_calls`
# as "done, no tool needed" in that case would silently skip real retrieval
# and let a hallucinated-looking answer through, so this is parsed and
# executed as a real tool call instead of being ignored.
TEXT_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _extract_text_tool_call(content: str) -> dict | None:
    match = TEXT_TOOL_CALL_RE.search(content or "")
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if "name" not in parsed:
        return None
    return {
        "id": "textual_tool_call",
        "function": {"name": parsed["name"], "arguments": parsed.get("arguments", {})},
    }


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


def _ollama_chat(messages: list[dict], tools: list[dict] | None, stream: bool):
    # Real finding: qwen3:8b's default "thinking" mode took 53s to produce a
    # single tool call (vs. 5.4s with thinking off) - the CHAT-7 accept bar
    # (first token under 3s) is only reachable with it disabled.
    payload = {"model": OLLAMA_MODEL, "messages": messages, "stream": stream, "think": False}
    if tools:
        payload["tools"] = tools
    return payload


def _run_tool_phase(messages: list[dict]) -> list[dict]:
    """Up to MAX_TOOL_CALLS tool calls, non-streamed so tool_calls JSON is
    always complete. Returns the final message list, ready for the
    streamed answer phase."""
    tool_calls_used = 0
    with httpx.Client(timeout=60.0) as client:
        while tool_calls_used < MAX_TOOL_CALLS:
            resp = client.post(
                f"{OLLAMA_URL}/v1/chat/completions",
                json=_ollama_chat(messages, TOOL_SCHEMAS, stream=False),
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                fallback = _extract_text_tool_call(msg.get("content", ""))
                if fallback is None:
                    break
                tool_calls = [fallback]

            messages.append(msg)
            for tc in tool_calls:
                if tool_calls_used >= MAX_TOOL_CALLS:
                    break
                tool_calls_used += 1
                fn = tc["function"]
                try:
                    args = json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
                    result = call_tool(fn["name"], args)
                except Exception as e:  # noqa: BLE001 - surfaced to the model, not the user
                    print(f"[chat] tool call failed: {fn['name']}({fn['arguments']!r}) -> {e}", flush=True)
                    result = {"error": str(e)}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result, default=str)[:4000],
                })
    return messages


def _validate_citations(session: Session, text_content: str) -> list[str]:
    """CHAT-6: never trust an LLM-returned key without checking it."""
    candidate_keys = set(CITATION_KEY_RE.findall(text_content))
    if not candidate_keys:
        return []
    rows = session.execute(
        text("SELECT dblp_key FROM paper WHERE dblp_key = ANY(:keys)"),
        {"keys": list(candidate_keys)},
    ).all()
    valid = {r[0] for r in rows}
    for key in candidate_keys - valid:
        print(f"[chat] dropped hallucinated citation key: {key}", flush=True)
    return sorted(valid)


_TOOL_CALL_PREFIX_CHECK_LEN = 20


def _stream_answer(messages: list[dict], session: Session):
    """Streams the final answer. `tools=None` here so the model can't return
    a structured tool_calls response mid-stream - but qwen3:8b can still
    (rarely) emit a leaked `<tool_call>...` text block instead of prose (see
    TEXT_TOOL_CALL_RE above). Buffers just enough of the start of the
    response to detect that pattern before forwarding anything, so such a
    leak is never shown to the user raw."""
    final_messages = messages + [
        {"role": "system", "content": "Answer now, in prose, using only what the tools returned above."}
    ]
    accumulated = []
    pending_prefix = ""
    prefix_checked = False

    with httpx.Client(timeout=60.0) as client:
        with client.stream(
            "POST", f"{OLLAMA_URL}/v1/chat/completions",
            json=_ollama_chat(final_messages, tools=None, stream=True),
        ) as resp:
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload.strip() == "[DONE]":
                    break
                chunk = json.loads(payload)
                delta = chunk["choices"][0]["delta"].get("content")
                if not delta:
                    continue
                accumulated.append(delta)

                if prefix_checked:
                    yield f"data: {json.dumps({'type': 'token', 'content': delta})}\n\n"
                    continue

                pending_prefix += delta
                if len(pending_prefix) < _TOOL_CALL_PREFIX_CHECK_LEN and "<tool_call>" not in pending_prefix:
                    continue
                prefix_checked = True
                if pending_prefix.lstrip().startswith("<tool_call>"):
                    # Suppress this whole response - it's a leaked tool call,
                    # not prose. Nothing streamed yet, so nothing to retract.
                    continue
                yield f"data: {json.dumps({'type': 'token', 'content': pending_prefix})}\n\n"

    full_text = "".join(accumulated)
    if full_text.lstrip().startswith("<tool_call>"):
        print("[chat] suppressed a leaked <tool_call> block from the final answer", flush=True)
        yield f"data: {json.dumps({'type': 'token', 'content': 'I found some information but had trouble composing an answer - could you rephrase your question?'})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'citations': []})}\n\n"
        return

    citations = _validate_citations(session, full_text)
    yield f"data: {json.dumps({'type': 'done', 'citations': citations})}\n\n"


@router.post("")
def chat(req: ChatRequest, session: Session = Depends(get_session)):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += req.history[-MAX_HISTORY_TURNS * 2:]
    messages.append({"role": "user", "content": req.message})

    messages = _run_tool_phase(messages)

    return StreamingResponse(_stream_answer(messages, session), media_type="text/event-stream")
