import uuid
import os
import json
import urllib.error
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional, Dict, Any, List
from schemas import FrontendChatRequest, FrontendLearnRequest, FrontendExecuteRequest, AgentRequest
from config import config
from tool_router import ToolRouter
from orchestrator import Orchestrator
from memory_manager import MemoryManager
from memory_core import MemoryCore

app = FastAPI(title="Nightion Agent API")
memory_db = MemoryManager()
memory_core = MemoryCore()
router = ToolRouter()
orchestrator = Orchestrator(router=router)

# Mount Static UI
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.get("/api/ping")
async def ping():
    return {"ping": "pong", "version": "30.0"}

@app.get("/api/health")
async def health():
    import urllib.request
    import asyncio

    def _check_ollama() -> bool:
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2) as r:
                return r.status == 200
        except Exception:
            return False

    ollama_ok = await asyncio.to_thread(_check_ollama)
    model_name = getattr(config, "MODEL_NAME", "gemma4")
    return {
        "ollama":         "online" if ollama_ok else "offline",
        "model_ready":    ollama_ok,
        "internet_ready": False,
        "model":          model_name,
        "status":         "READY" if ollama_ok else "OFFLINE",
    }

@app.get("/api/stats")
async def get_stats():
    return {
        "model": getattr(config, "MODEL_NAME", "gemma4"),
        "rag_stats": {"total_chunks": 0},
        "conversation_turns": 0,
    }

@app.post("/api/execute")
async def execute_code(req: FrontendExecuteRequest):
    return {"success": True, "stdout": "Sandbox placeholder.", "duration": 0.1}

@app.delete("/api/history")
async def clear_history():
    return {"success": True}

@app.get("/api/session/history")
async def get_session_history(session_id: str = "default_session"):
    history = memory_core.fetch_session_history(session_id, limit=50)
    return history

# --- Telemetry APIs ---
def _load_trace_segment(trace_id: str, segment_name: str, default: Any) -> Any:
    log_file = os.path.join(os.path.dirname(__file__), "logs", trace_id, f"{segment_name}.json")
    if not os.path.exists(log_file):
        return default
    try:
        with open(log_file, "r") as f:
            return json.load(f)
    except Exception:
        return default

@app.get("/api/traces")
async def list_all_traces():
    index_file = os.path.join(os.path.dirname(__file__), "logs", "index.json")
    if not os.path.exists(index_file):
        return []
    with open(index_file, "r") as f:
        try:
            data = json.load(f)
            return [t["trace_id"] for t in data if "trace_id" in t]
        except Exception:
            return []

@app.get("/api/traces/{trace_id}")
async def get_full_trace(trace_id: str):
    plan = _load_trace_segment(trace_id, "plan", [])
    return {
        "trace_id": trace_id,
        "status": "ok",
        "query": _load_trace_segment(trace_id, "request", {}).get("query", "Unknown"),
        "request": _load_trace_segment(trace_id, "request", {}),
        "router": _load_trace_segment(trace_id, "router", {}),
        "plan": plan,
        "cognition": plan[0] if isinstance(plan, list) and plan else {},
        "execution": _load_trace_segment(trace_id, "tool_runs", []),
        "final_response": _load_trace_segment(trace_id, "response", {}),
    }

@app.get("/api/logs/index")
async def list_traces_legacy():
    index_file = os.path.join(os.path.dirname(__file__), "logs", "index.json")
    if not os.path.exists(index_file):
        return []
    with open(index_file, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return []

@app.get("/api/logs/{trace_id}/{artifact_name}")
async def get_trace_artifact(trace_id: str, artifact_name: str):
    safe_artifacts = ["request.json", "router.json", "plan.json", "tool_runs.json", "response.json"]
    if artifact_name not in safe_artifacts:
        raise HTTPException(status_code=403, detail="Forbidden artifact.")
    log_file = os.path.join(os.path.dirname(__file__), "logs", trace_id, artifact_name)
    if not os.path.exists(log_file):
        raise HTTPException(status_code=404, detail="Trace artifact not found.")
    with open(log_file, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return None

# --- Agent Chat WebSocket ---
@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            chat_req = FrontendChatRequest(**data)

            trace_id_str = str(uuid.uuid4())
            memory_core.log_chat_event(chat_req.session_id, "user", chat_req.message, trace_id_str)

            session_history = memory_core.fetch_session_history(chat_req.session_id, limit=10)
            history_payload = [{"role": row["role"], "content": row["content"]} for row in session_history]

            agent_req = AgentRequest(
                trace_id=trace_id_str,
                query=chat_req.message,
                history=history_payload,
                session_id=chat_req.session_id,
            )

            print(f"[WS] Query: '{chat_req.message}'")

            # Streaming callback — forwards live think/response tokens directly to the UI
            async def send_streaming_token(msg: dict):
                msg_type = msg.get("type", "token")
                content  = msg.get("content", "")
                if msg_type in ("token", "think_token"):
                    await websocket.send_json({"type": msg_type, "content": content})
                # ignore 'feedback' type (internal status messages)

            response = await orchestrator.execute_task(agent_req, ui_feedback_cb=send_streaming_token)
            print(f"[WS] Response ready. Length: {len(response.result) if response.result else 0}")

            memory_core.log_chat_event(chat_req.session_id, "assistant", response.result, trace_id_str)

            # Signal the frontend that generation is complete
            await websocket.send_json({
                "type": "done",
                "rag_used": chat_req.use_rag,
                "trace_id": trace_id_str,
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"FATAL WS ERROR: {e}")
        try:
            await websocket.send_json({"type": "error", "content": f"Error: {str(e)}"})
        except Exception:
            pass


# --- Mode Switcher APIs ---
@app.get("/api/config")
async def get_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/screenshot")
async def take_screenshot():
    import asyncio
    import base64
    import io
    import urllib.request

    try:
        import pyautogui
        pyautogui.FAILSAFE = True
    except ImportError:
        return {"success": False, "analysis": "", "error": "pyautogui not installed"}

    try:
        from PIL import Image
    except ImportError:
        return {"success": False, "analysis": "", "error": "Pillow not installed"}

    try:
        screenshot = pyautogui.screenshot()
        w, h = screenshot.size
        if w > 1280:
            ratio = 1280 / w
            screenshot = screenshot.resize((1280, int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        screenshot.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        return {"success": False, "analysis": "", "error": f"Screenshot failed: {e}"}

    model_name = getattr(config, "MODEL_NAME", "gemma4")
    analysis_text = ""

    try:
        vision_payload = json.dumps({
            "model": "llava",
            "prompt": "Describe what you see on this screen concisely.",
            "images": [img_b64],
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=vision_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
            analysis_text = result.get("response", "")
    except Exception:
        try:
            fallback_payload = json.dumps({
                "model": model_name,
                "prompt": "Generate a helpful code template for the user to adapt.",
                "stream": False,
                "options": {"num_predict": 200},
            }).encode()
            req2 = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=fallback_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req2, timeout=20) as resp2:
                result2 = json.loads(resp2.read().decode())
                analysis_text = "[Vision model unavailable] " + result2.get("response", "Describe your problem in chat.")
        except Exception as e2:
            analysis_text = f"[Vision unavailable] ({e2})"

    return {"success": True, "analysis": analysis_text, "screenshot_size": list(screenshot.size)}


@app.post("/api/vision-code")
async def generate_vision_code(req: dict):
    import re
    import urllib.request

    analysis = req.get("analysis", "")
    language = req.get("language", "python")
    direct = req.get("direct", False)
    model_name = getattr(config, "MODEL_NAME", "gemma4")

    prompt = (
        f"Write a complete, clean, working {language} solution for: {analysis}\nReturn ONLY the code."
        if direct else
        f"Based on this screen analysis:\n{analysis}\n\nWrite a complete {language} solution. Return ONLY raw code."
    )

    try:
        payload = json.dumps({
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 1024, "temperature": 0.2},
        }).encode()
        req_obj = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req_obj, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            raw_code = result.get("response", "")

        code_match = re.search(r"```[\w]*\n?([\s\S]*?)```", raw_code)
        clean_code = code_match.group(1).strip() if code_match else raw_code.strip()

        detected_lang = language
        if "def " in clean_code or "import " in clean_code:
            detected_lang = "python"
        elif "#include" in clean_code:
            detected_lang = "cpp"
        elif "public class" in clean_code:
            detected_lang = "java"

        return {"success": True, "code": clean_code, "language": detected_lang}
    except Exception as e:
        return {"success": False, "code": "", "language": language, "error": str(e)}


@app.post("/api/see-and-code")
async def see_and_code_endpoint(request_body: dict):
    """
    See & Code pipeline: screenshot → vision AI → extract code.
    Accepts: { "language": "python", "no_switch": bool }
    Returns: { "success": bool, "code": str, "language": str, "analysis": str }
    """
    import asyncio

    language = request_body.get("language", "python")
    no_switch = request_body.get("no_switch", False)
    model_name = "gemma4"

    # Import see_and_code safely — prevents 500 if dependencies are missing
    try:
        from see_and_code import capture_screen, generate_code_from_image
    except ImportError as e:
        print(f"[see-and-code] Import error: {e}")
        return {"success": False, "code": "", "language": language, "analysis": "", "error": f"Missing dependency: {e}"}
    except Exception as e:
        print(f"[see-and-code] Unexpected import error: {e}")
        return {"success": False, "code": "", "language": language, "analysis": "", "error": f"Module load error: {e}"}

    # Step 1: Capture screen
    try:
        # no_switch=True when called from Smart Cursor panel (user is already
        # looking at the target screen; Alt+Tab would switch AWAY from it)
        img_b64, size = await asyncio.to_thread(
            capture_screen,
            1280,               # max_width
            not no_switch,      # switch_window: False for smart cursor
        )
    except Exception as e:
        print(f"[see-and-code] Screenshot failed: {e}")
        return {"success": False, "code": "", "language": language, "analysis": "", "error": f"Screenshot failed: {e}"}

    # Step 2: Generate code from screenshot (gemma4 only, no llava)
    try:
        result = await asyncio.to_thread(
            generate_code_from_image,
            img_b64,
            language,
            model_name,
        )
        # Ensure result is always a dict with correct shape
        if not isinstance(result, dict):
            result = {"success": False, "code": "", "language": language, "analysis": "", "error": "Unexpected model response format"}
        return result
    except urllib.error.URLError as e:
        print(f"[see-and-code] Ollama unreachable: {e}")
        return {"success": False, "code": "", "language": language, "analysis": "", "error": f"Ollama is not running or unreachable: {e}"}
    except Exception as e:
        print(f"[see-and-code] Code generation failed: {e}")
        return {"success": False, "code": "", "language": language, "analysis": "", "error": f"Code generation failed: {e}"}


@app.post("/api/type-humanlike")
async def type_humanlike_endpoint(request_body: dict):
    """
    Wait for user to click in an external app, then type code
    character-by-character with human-like timing.
    Accepts: { "code": "..." }
    """
    import asyncio
    from see_and_code import wait_for_external_click_then_type

    code = request_body.get("code", "")
    if not code or not code.strip():
        return {"success": False, "error": "No code provided", "chars_typed": 0}

    try:
        result = await asyncio.to_thread(wait_for_external_click_then_type, code, 120)
        return result
    except Exception as e:
        return {"success": False, "error": str(e), "chars_typed": 0}


@app.post("/api/type-humanlike/cancel")
async def cancel_humanlike_typing():
    """Cancel an in-progress humanlike typing session."""
    from see_and_code import cancel_typing
    cancel_typing()
    return {"success": True, "message": "Cancel signal sent"}


@app.post("/api/type-anywhere")
async def type_anywhere(request_body: dict):
    import asyncio
    import platform

    code = request_body.get("code", "")
    if not code or not code.strip():
        return {"success": False, "error": "No code provided"}

    try:
        import pyautogui
        import pyperclip
        pyautogui.FAILSAFE = True
    except ImportError as e:
        return {"success": False, "error": f"Missing dependency: {e}"}

    try:
        pyperclip.copy(code)
        await asyncio.sleep(0.15)
        if platform.system() == "Darwin":
            pyautogui.hotkey("command", "v")
        else:
            pyautogui.hotkey("ctrl", "v")
        return {"success": True, "method": "clipboard_paste", "chars_typed": len(code)}
    except Exception as e_clip:
        try:
            lines = code.split("\n")
            for i, line in enumerate(lines):
                safe_line = "".join(c for c in line if 32 <= ord(c) <= 126)
                pyautogui.typewrite(safe_line, interval=0.01)
                if i < len(lines) - 1:
                    pyautogui.press("enter")
            return {"success": True, "method": "typewrite_fallback", "chars_typed": len(code)}
        except Exception as e_type:
            return {"success": False, "error": f"Clipboard: {e_clip} | Typewrite: {e_type}"}


@app.post("/api/vision")
async def vision_endpoint(request_body: dict):
    """
    Smart Cursor vision endpoint — gemma4 multimodal reasoning with
    optional verification pass.

    Accepts: { "image": "<base64 PNG>", "prompt": "<question>" }
    Returns: { "success": bool, "answer": str, "pass1": str, "error": str|None }

    Pass 1: Send image + prompt to gemma4 (multimodal vision)
    Pass 2: ONLY if Pass 1 answer is short/suspicious — verify via text-only gemma4
    """
    import asyncio
    import base64 as b64mod
    import re
    import urllib.request
    import urllib.error

    image_b64 = request_body.get("image", "")
    prompt = request_body.get("prompt", "Describe what you see and answer any questions shown.")

    if not image_b64:
        return {"success": False, "answer": "", "pass1": "", "error": "No image provided"}

    # ── Validate image before sending to Ollama ───────────────────────────
    if len(image_b64) < 100:
        print(f"[Vision] Image base64 too small: {len(image_b64)} chars")
        return {"success": False, "answer": "", "pass1": "", "error": f"Image too small ({len(image_b64)} chars)"}

    try:
        raw_img_bytes = b64mod.b64decode(image_b64)
        print(f"[Vision] Image validated: {len(image_b64)} chars b64 → {len(raw_img_bytes)} bytes ({len(raw_img_bytes)//1024} KB)")

        # Check it's actually a PNG/JPEG by inspecting magic bytes
        if raw_img_bytes[:4] == b'\x89PNG':
            print("[Vision] ✓ Image format: PNG")
        elif raw_img_bytes[:2] == b'\xff\xd8':
            print("[Vision] ✓ Image format: JPEG")
        else:
            print(f"[Vision] ⚠ Unknown image format (magic: {raw_img_bytes[:4].hex()})")

        # Try to get dimensions via PIL
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(raw_img_bytes))
            print(f"[Vision] ✓ Image dimensions: {img.size[0]}x{img.size[1]}, mode={img.mode}")
            if img.size[0] < 10 or img.size[1] < 10:
                return {"success": False, "answer": "", "pass1": "", "error": f"Image too small: {img.size[0]}x{img.size[1]}"}
        except Exception as pil_err:
            print(f"[Vision] ⚠ Could not read image dimensions: {pil_err}")
    except Exception as decode_err:
        print(f"[Vision] ✗ Base64 decode failed: {decode_err}")
        return {"success": False, "answer": "", "pass1": "", "error": f"Invalid image encoding: {decode_err}"}

    model = "gemma4"

    def _strip_think_tags(text: str) -> str:
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', text)
        cleaned = re.sub(r'</?think>', '', cleaned)
        return cleaned.strip()

    # ── Pass 1: Vision — image + prompt → gemma4 ──────────────────────────
    def _pass1():
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_predict": 4096},
        }).encode()

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        print(f"[Vision] Sending to Ollama: model={model}, prompt_len={len(prompt)}, image_size={len(image_b64)} chars")

        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read().decode())
            raw = result.get("response", "")
            print(f"[Vision] Ollama raw response: {len(raw)} chars")
            return _strip_think_tags(raw)

    # ── Pass 2: Verify — text-only re-check → gemma4 ─────────────────────
    def _pass2(pass1_answer: str):
        verify_prompt = (
            f"You previously answered a question from a screenshot and gave this response:\n\n"
            f"---\n{pass1_answer}\n---\n\n"
            f"Review this answer. Fix ONLY genuine errors:\n"
            f"- Factual mistakes or wrong calculations\n"
            f"- Missing critical information\n"
            f"- Typos in the answer\n\n"
            f"IMPORTANT: Do NOT shorten the answer. Do NOT remove detail. "
            f"Do NOT add preambles like 'Here is...' or 'The corrected answer is...'. "
            f"Do NOT add markdown formatting. "
            f"If the answer is already correct, return it EXACTLY as-is. "
            f"Output ONLY the final answer text."
        )

        payload = json.dumps({
            "model": model,
            "prompt": verify_prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1, "num_predict": 4096},
        }).encode()

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return _strip_think_tags(result.get("response", ""))

    try:
        # Run Pass 1 (vision)
        pass1_answer = await asyncio.to_thread(_pass1)
        if not pass1_answer or not pass1_answer.strip():
            return {"success": False, "answer": "", "pass1": "", "error": "Vision model returned empty response"}

        pass1_clean = pass1_answer.strip()
        print(f"[Vision] Pass 1 ({len(pass1_clean)} chars): {pass1_clean[:120]}...")

        # ── Decide whether to run Pass 2 ─────────────────────────────────
        # Skip verification for confident, longer answers — Pass 2 often
        # truncates good answers or rewrites them into short summaries.
        # Only verify if answer is suspiciously short or looks incomplete.
        needs_verify = (
            len(pass1_clean) < 50 or                        # Very short — might be wrong
            pass1_clean.endswith("...") or                   # Truncated
            "I cannot" in pass1_clean or                     # Refusal
            "I'm not sure" in pass1_clean or                 # Uncertainty
            pass1_clean.count("\n") == 0 and len(pass1_clean) < 100  # Single short line
        )

        if needs_verify:
            print(f"[Vision] Running Pass 2 verification (answer is short/suspicious)")
            pass2_answer = await asyncio.to_thread(_pass2, pass1_clean)
            final_answer = pass2_answer.strip() if pass2_answer and pass2_answer.strip() else pass1_clean
            print(f"[Vision] Pass 2 ({len(final_answer)} chars): {final_answer[:120]}...")

            # Guard: if Pass 2 made the answer much shorter, keep Pass 1
            if len(final_answer) < len(pass1_clean) * 0.5 and len(pass1_clean) > 30:
                print(f"[Vision] ⚠ Pass 2 truncated answer ({len(final_answer)} < {len(pass1_clean)}*0.5), keeping Pass 1")
                final_answer = pass1_clean
        else:
            print(f"[Vision] Skipping Pass 2 — Pass 1 answer is confident ({len(pass1_clean)} chars)")
            final_answer = pass1_clean

        return {
            "success": True,
            "answer": final_answer,
            "pass1": pass1_clean,
            "error": None,
        }
    except Exception as e:
        print(f"[Vision] Error: {e}")
        return {"success": False, "answer": "", "pass1": "", "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("nightion_core:app", host="0.0.0.0", port=8999, reload=False)
