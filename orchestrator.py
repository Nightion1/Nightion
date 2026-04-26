"""
orchestrator.py — Nightion Offline-Only Orchestrator
Handles all queries locally via Ollama (gemma4).
No web search, no external learning, no internet dependency.
Streams reasoning and response tokens live to the UI.
"""
import asyncio
import json
import logging
import urllib.request
from typing import Optional, Callable

from schemas import (
    AgentRequest, AgentResponse, RouterDecision,
    StatusEnum, NextActionEnum, IntentEnum, AgentRole
)
from tool_router import ToolRouter
from memory_core import MemoryCore

log = logging.getLogger("nightion.orchestrator")

MODEL_NAME  = "gemma4"
OLLAMA_URL  = "http://localhost:11434/api/generate"

SYSTEM_PROMPT = (
    "You are Nightion, a powerful AI coding assistant created by Nitin (solo developer). "
    "Your underlying model is gemma4 running entirely offline via Ollama. "
    "You are NOT made by Google, Anthropic, OpenAI, or any company. "
    "When asked who made you: 'I am Nightion, built by Nitin. My model is gemma4 via Ollama.' "
    "Answer user queries directly and helpfully. "
    "Format code with triple backtick fences and the language tag (e.g. ```python). "
    "For conceptual or general questions, respond conversationally in markdown. "
    "Be concise but thorough."
)


class Orchestrator:
    """
    Minimal offline-only Nightion orchestrator.
    Routes every query to local Ollama (gemma4) and returns the result.
    Streams reasoning and response tokens live to the UI.
    """

    def __init__(self, router: ToolRouter, max_retries: int = 2, role: AgentRole = AgentRole.PRIMARY_ORCHESTRATOR):
        self.router     = router
        self.max_retries = max_retries
        self.role       = role
        self.memory     = MemoryCore()

    # ------------------------------------------------------------------
    # Public API — called by nightion_core.py WebSocket handler
    # ------------------------------------------------------------------

    async def execute_task(
        self,
        request: AgentRequest,
        forced_intent: IntentEnum = None,
        ui_feedback_cb: Optional[Callable] = None,
    ) -> AgentResponse:
        """Main entry point. Sends query to Ollama and returns response."""

        query      = request.query.strip()
        session_id = getattr(request, "session_id", "default_session") or "default_session"

        # Build conversation context from recent history
        history_context = ""
        session_history = self.memory.fetch_session_history(session_id, limit=8)
        if session_history:
            lines = []
            for msg in session_history[:-1]:   # exclude the current message itself
                role    = msg.get("role", "user")
                content = msg.get("content", "").strip()
                if content and len(content) < 600:
                    lines.append(f"{role.capitalize()}: {content}")
            if lines:
                history_context = "\n".join(lines[-6:])

        # Log the user message
        self.memory.log_chat_event(session_id, "user", query, request.trace_id)

        try:
            result = await self._call_ollama_streaming(query, history_context, ui_feedback_cb)
        except ConnectionRefusedError:
            result = (
                "⚠️ Ollama is not running. Please start it with `ollama serve` "
                "then refresh and try again."
            )
        except Exception as e:
            log.error("[Orchestrator] Ollama call failed: %s", e)
            result = (
                f"⚠️ Could not reach Ollama ({type(e).__name__}). "
                "Make sure `ollama serve` is running and `gemma4` is pulled."
            )

        # Log the assistant response
        self.memory.log_chat_event(session_id, "assistant", result, request.trace_id)

        return AgentResponse(
            trace_id=request.trace_id,
            status=StatusEnum.OK,
            result=result,
            confidence=0.95,
            next_action=NextActionEnum.RESPOND,
            metadata={"model": MODEL_NAME, "session_id": session_id},
        )

    # ------------------------------------------------------------------
    # Ollama Integration  (streaming — real-time reasoning + response)
    # ------------------------------------------------------------------

    async def _call_ollama_streaming(
        self,
        query: str,
        history_context: str,
        ui_callback: Optional[Callable] = None,
    ) -> str:
        """
        Call Ollama /api/generate with stream=True + think=True.

        Ollama streams NDJSON lines. Each line may have:
          - "thinking" : str  — reasoning token (Ollama think-mode field)
          - "response" : str  — actual answer token
          - "done"     : bool — signals end of stream

        We forward each piece to the WebSocket in real-time:
          thinking  → {type: "think_token", content: ...}
          response  → {type: "token",       content: ...}

        Both inline <think>…</think> (qwen3-style) AND Ollama's separate
        "thinking" field (gemma/qwen think-mode) are handled.
        """
        # Build prompt
        if history_context:
            full_prompt = (
                f"{SYSTEM_PROMPT}\n\n"
                f"## Conversation History\n{history_context}\n\n"
                f"## Current Query\nUser: {query}\nAssistant:"
            )
        else:
            full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {query}\nAssistant:"

        payload = {
            "model":  MODEL_NAME,
            "prompt": full_prompt,
            "stream": True,
            "think":  True,          # enable Ollama native think-mode
            "options": {
                "temperature": 0.7,
                "num_predict": 2048,
                "top_p": 0.9,
            },
        }

        think_buf = ""   # accumulated reasoning text
        resp_buf  = ""   # accumulated response text

        # ── Async streaming loop ──────────────────────────────────────────
        # asyncio.to_thread for each blocking read so the event loop stays
        # free to forward WebSocket messages between reads.
        import http.client as _http
        import urllib.parse as _up

        _parsed = _up.urlparse(OLLAMA_URL)

        def _open_conn():
            c = _http.HTTPConnection(_parsed.hostname, _parsed.port, timeout=300)
            _body = json.dumps(payload).encode("utf-8")
            c.request("POST", _parsed.path, body=_body,
                      headers={"Content-Type": "application/json"})
            return c, c.getresponse()

        conn, http_resp = await asyncio.to_thread(_open_conn)

        leftover = ""
        try:
            while True:
                # Read up to 4 KB — large enough for multiple tokens per await
                chunk = await asyncio.to_thread(http_resp.read, 4096)
                if not chunk:
                    break

                text  = leftover + chunk.decode("utf-8", errors="replace")
                lines = text.split("\n")
                leftover = lines[-1]   # may be an incomplete JSON line

                for line in lines[:-1]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # ── Thinking field (Ollama native think-mode) ─────────
                    think_tok = data.get("thinking") or ""
                    if think_tok:
                        think_buf += think_tok
                        if ui_callback:
                            await ui_callback({"type": "think_token", "content": think_tok})

                    # ── Response field ────────────────────────────────────
                    resp_tok = data.get("response") or ""
                    if resp_tok:
                        # Also handle inline <think>…</think> (qwen3-style)
                        # by stripping out those tags before forwarding.
                        import re as _re
                        # Extract any inline think content not already captured
                        inline_thinks = _re.findall(r"<think>([\s\S]*?)</think>", resp_tok)
                        for it in inline_thinks:
                            if it not in think_buf:
                                think_buf += it
                                if ui_callback:
                                    await ui_callback({"type": "think_token", "content": it})
                        # Strip <think> blocks from visible response
                        # Do NOT .strip() — whitespace tokens (spaces, newlines) are essential for formatting
                        clean_tok = _re.sub(r"<think>[\s\S]*?</think>", "", resp_tok)
                        if clean_tok:
                            resp_buf += clean_tok
                            if ui_callback:
                                await ui_callback({"type": "token", "content": clean_tok})

                    if data.get("done"):
                        break
        finally:
            await asyncio.to_thread(conn.close)

        # ── Assemble stored result ────────────────────────────────────────
        if not resp_buf.strip() and not think_buf.strip():
            log.error(
                "[Orchestrator] Ollama returned empty streaming response. Model: %s",
                MODEL_NAME,
            )
            return (
                "⚠️ The model returned an empty response. "
                "Try rephrasing your query, or check that `gemma4` is fully loaded."
            )

        if think_buf.strip():
            return f"<think>{think_buf.strip()}</think>\n\n{resp_buf.strip()}"
        return resp_buf.strip()

    # ------------------------------------------------------------------
    # Legacy helper — kept for backward-compat
    # ------------------------------------------------------------------

    async def _run_llm(
        self,
        prompt: str,
        system_msg: str = "",
        temperature: float = 0.7,
        role=None,
    ) -> str:
        full_prompt = f"{system_msg}\n\n{prompt}" if system_msg else prompt
        payload = {
            "model":  MODEL_NAME,
            "prompt": full_prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 800},
        }

        def _call():
            req = urllib.request.Request(
                OLLAMA_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8")).get("response", "").strip()

        try:
            return await asyncio.to_thread(_call)
        except Exception as e:
            return f"LLM call failed: {e}"
