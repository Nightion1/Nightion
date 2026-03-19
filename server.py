"""
Nightion — FastAPI Backend Server
Always-on local AI coding assistant powered by Ollama + DeepSeek-Coder
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from code_runner import run_python
from rag_engine import NightionRAG

# ── Config ────────────────────────────────────────────────────────────────────
OLLAMA_BASE = "http://localhost:11434"
MODEL = "gemma3:4b"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Nightion", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

rag = NightionRAG()
conversation_history: list[dict] = []

# ── Schemas ───────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    use_rag: bool = True

class LearnRequest(BaseModel):
    text: str
    source: Optional[str] = "user"

class ExecuteRequest(BaseModel):
    code: str
    timeout: Optional[int] = 10

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Nightion, an elite AI coding assistant.
Your goal is to provide high-quality, efficient, and correct code solutions.
Always explain the logic behind your code and use markdown for formatting.
If given knowledge base context, use it to ground and verify your answer.
"""

def build_messages(user_message: str, rag_context: list[str]) -> list[dict]:
    """Build message list for Ollama."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    # Add RAG context if available
    if rag_context:
        ctx_text = "\n\n---\n".join(rag_context)
        messages.append({
            "role": "system",
            "content": f"[Knowledge Base Context]\n{ctx_text}"
        })
    
    # Add conversation history (last 6 turns for speed)
    for turn in conversation_history[-6:]:
        messages.append(turn)
    
    messages.append({"role": "user", "content": user_message})
    return messages

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Non-streaming chat endpoint."""
    # Skip RAG for simple greetings/short messages to save time
    is_greeting = len(req.message) < 15 and req.message.lower().strip() in ["hi", "hello", "hey", "yo", "sup", "hi nightion", "hello nightion"]
    should_use_rag = req.use_rag and not is_greeting
    
    rag_ctx = rag.retrieve(req.message) if should_use_rag else []
    messages = build_messages(req.message, rag_ctx)
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{OLLAMA_BASE}/api/chat",
            json={"model": MODEL, "messages": messages, "stream": False, "keep_alive": -1}
        )
        data = resp.json()
    
    answer = data.get("message", {}).get("content", "")
    
    # Store in history
    conversation_history.append({"role": "user", "content": req.message})
    conversation_history.append({"role": "assistant", "content": answer})
    
    return {"response": answer, "rag_used": len(rag_ctx) > 0}


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """Streaming chat via WebSocket."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            user_message = payload.get("message", "")
            use_rag = payload.get("use_rag", True)

            # Skip RAG for simple greetings/short messages to save time
            is_greeting = len(user_message) < 15 and user_message.lower().strip() in ["hi", "hello", "hey", "yo", "sup", "hi nightion", "hello nightion"]
            should_use_rag = use_rag and not is_greeting

            rag_ctx = rag.retrieve(user_message) if should_use_rag else []
            messages = build_messages(user_message, rag_ctx)

            full_response = ""
            
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE}/api/chat",
                    json={"model": MODEL, "messages": messages, "stream": True, "keep_alive": -1}
                ) as resp:
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                full_response += token
                                await websocket.send_text(json.dumps({
                                    "type": "token",
                                    "content": token
                                }))
                            if chunk.get("done"):
                                await websocket.send_text(json.dumps({
                                    "type": "done",
                                    "rag_used": len(rag_ctx) > 0
                                }))
                        except json.JSONDecodeError:
                            continue

            # Save to history
            conversation_history.append({"role": "user", "content": user_message})
            conversation_history.append({"role": "assistant", "content": full_response})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))
        except:
            pass


@app.post("/api/learn")
async def learn(req: LearnRequest):
    """Teach Nightion new knowledge."""
    chunks = rag.learn(req.text, req.source or "user")
    stats = rag.get_stats()
    return {
        "success": True,
        "chunks_stored": chunks,
        "total_knowledge": stats["total_chunks"],
        "message": f"✅ Nightion learned {chunks} new chunk(s). Total knowledge: {stats['total_chunks']} chunks."
    }


@app.post("/api/execute")
async def execute(req: ExecuteRequest):
    """Execute Python code."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, lambda: run_python(req.code, req.timeout or 10)
    )
    return result


@app.get("/api/stats")
async def stats():
    return {
        "model": MODEL,
        "ollama_url": OLLAMA_BASE,
        "rag_stats": rag.get_stats(),
        "conversation_turns": len(conversation_history) // 2,
        "status": "online"
    }


@app.delete("/api/history")
async def clear_history():
    conversation_history.clear()
    return {"success": True, "message": "Conversation history cleared."}


@app.delete("/api/memory")
async def clear_memory():
    rag.clear()
    return {"success": True, "message": "Nightion's memory cleared."}


@app.get("/api/health")
async def health():
    """Check if Ollama is running."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            models = [m["name"] for m in resp.json().get("models", [])]
            model_ready = any(MODEL.split(":")[0] in m for m in models)
            return {"ollama": "online", "model_ready": model_ready, "models": models}
    except Exception as e:
        return {"ollama": "offline", "error": str(e), "model_ready": False}


# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("""
+----------------------------------------------+
|      NIGHTION  --  AI CODING BRAIN           |
|      Powered by DeepSeek-Coder               |
+----------------------------------------------+
|  Starting server at http://localhost:8000    |
|  Press Ctrl+C to stop                        |
+----------------------------------------------+
    """)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
