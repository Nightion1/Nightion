# -*- coding: utf-8 -*-
"""
smart_cursor.py — Nightion Smart Cursor Mode
Global hotkey Ctrl+Shift+0 → area selector overlay → mss screenshot →
POST to Nightion /api/vision → click-to-type result anywhere.

Runs as a background process. Does NOT need Nightion UI to be focused.

Dependencies: keyboard, mss, pynput, pyautogui, requests, tkinter (stdlib), Pillow
"""

import base64
import io
import json
import logging
import os
import random
import re
import sys
import threading
import time
import urllib.request
import urllib.error

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[SmartCursor] %(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smart_cursor")

# ── Config ────────────────────────────────────────────────────────────────────
NIGHTION_BACKEND = "http://127.0.0.1:8999"
VISION_ENDPOINT  = f"{NIGHTION_BACKEND}/api/vision"
HOTKEY           = "ctrl+shift+0"

# ── State ─────────────────────────────────────────────────────────────────────
_active_lock = threading.Lock()
_is_active   = False  # Prevent re-entrant triggers


# ═══════════════════════════════════════════════════════════════════════════════
#  1. TOAST NOTIFICATIONS (tkinter topmost label)
# ═══════════════════════════════════════════════════════════════════════════════

def _show_toast(message: str, duration: float = 2.5, bg: str = "#1a1a2e",
                fg: str = "#00ff88", width: int = 420):
    """
    Show a small topmost notification at the bottom-right of the screen.
    Non-blocking — runs in its own thread.
    """
    def _toast_thread():
        import tkinter as tk
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.92)
        root.configure(bg=bg)

        # Position: bottom-right with padding
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = screen_w - width - 24
        y = screen_h - 80
        root.geometry(f"{width}x48+{x}+{y}")

        label = tk.Label(
            root, text=f"  ✦ {message}  ", font=("Segoe UI", 11, "bold"),
            bg=bg, fg=fg, anchor="w", padx=12,
        )
        label.pack(fill="both", expand=True)

        root.after(int(duration * 1000), root.destroy)
        root.mainloop()

    t = threading.Thread(target=_toast_thread, daemon=True)
    t.start()


# ═══════════════════════════════════════════════════════════════════════════════
#  2. FULLSCREEN AREA SELECTOR OVERLAY (Snipping Tool style)
# ═══════════════════════════════════════════════════════════════════════════════

def select_screen_region() -> dict | None:
    """
    Show a fullscreen semi-transparent overlay. User clicks and drags to
    select a rectangular region. Returns {"x": int, "y": int, "w": int, "h": int}
    or None if cancelled (Escape / right-click).

    MUST run on the main thread (tkinter requirement on Windows).
    """
    import tkinter as tk

    result = {"region": None}

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.30)
    root.configure(bg="#000000", cursor="crosshair")
    root.overrideredirect(True)

    canvas = tk.Canvas(root, bg="#000000", highlightthickness=0,
                       cursor="crosshair")
    canvas.pack(fill="both", expand=True)

    # Instruction text
    canvas.create_text(
        root.winfo_screenwidth() // 2, 40,
        text="🎯 Click and drag to select a region  •  Press Esc to cancel",
        fill="#00ff88", font=("Segoe UI", 14, "bold"),
    )

    start = {"x": 0, "y": 0}
    rect_id = None

    def on_press(event):
        nonlocal rect_id
        start["x"] = event.x
        start["y"] = event.y
        if rect_id:
            canvas.delete(rect_id)
        rect_id = canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#00ff88", width=2, dash=(6, 4),
        )

    def on_drag(event):
        nonlocal rect_id
        if rect_id:
            canvas.coords(rect_id, start["x"], start["y"], event.x, event.y)

    def on_release(event):
        x1, y1 = start["x"], start["y"]
        x2, y2 = event.x, event.y
        # Normalize coordinates (handle drag in any direction)
        rx = min(x1, x2)
        ry = min(y1, y2)
        rw = abs(x2 - x1)
        rh = abs(y2 - y1)
        if rw > 5 and rh > 5:  # Minimum 5x5 selection
            result["region"] = {"x": rx, "y": ry, "w": rw, "h": rh}
        root.destroy()

    def on_escape(event):
        root.destroy()

    def on_right_click(event):
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<ButtonPress-3>", on_right_click)
    root.bind("<Escape>", on_escape)

    # Focus the overlay so it receives keyboard events
    root.focus_force()
    root.mainloop()

    return result["region"]


# ═══════════════════════════════════════════════════════════════════════════════
#  3. MSS SCREENSHOT OF SELECTED REGION
# ═══════════════════════════════════════════════════════════════════════════════

def capture_region(region: dict) -> str:
    """
    Capture a specific screen region using mss (GDI-based, works on games,
    browsers, DWM composited windows).

    Args:
        region: {"x": int, "y": int, "w": int, "h": int}

    Returns:
        Base64-encoded PNG string.
    """
    import mss
    from PIL import Image, ImageStat

    monitor = {
        "left": region["x"],
        "top":  region["y"],
        "width":  region["w"],
        "height": region["h"],
    }

    with mss.mss() as sct:
        raw = sct.grab(monitor)
        # mss returns BGRA; convert to RGB PIL Image
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # ── Validate capture is not blank/black ──────────────────────────────
    stat = ImageStat.Stat(img)
    mean_brightness = sum(stat.mean) / 3  # average across R, G, B
    stddev = sum(stat.stddev) / 3
    log.info(f"Capture stats — mean brightness: {mean_brightness:.1f}, stddev: {stddev:.1f}")

    if mean_brightness < 3 and stddev < 2:
        log.warning("Captured image appears to be entirely black/blank!")
    elif stddev < 5:
        log.warning(f"Captured image has very low variance (stddev={stddev:.1f}) — may be a solid color")

    # ── Save debug copy to disk for verification ─────────────────────────
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
    os.makedirs(debug_dir, exist_ok=True)
    debug_path = os.path.join(debug_dir, "smart_cursor_last_capture.png")
    try:
        img.save(debug_path, format="PNG")
        log.info(f"Debug capture saved → {debug_path}")
    except Exception as e:
        log.warning(f"Could not save debug capture: {e}")

    # Resize if wider than 1280 to keep payload reasonable
    max_w = 1280
    if img.width > max_w:
        ratio = max_w / img.width
        img = img.resize((max_w, int(img.height * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    # ── Verify base64 round-trips correctly ──────────────────────────────
    try:
        decoded = base64.b64decode(b64)
        verify_img = Image.open(io.BytesIO(decoded))
        log.info(f"✓ Base64 verified: {verify_img.size[0]}x{verify_img.size[1]}, "
                 f"{len(b64)} chars, ~{len(b64) * 3 // 4 // 1024} KB")
    except Exception as e:
        log.error(f"✗ Base64 verification FAILED: {e}")

    log.info(f"Captured region {region['w']}x{region['h']} → {len(b64)} chars base64")
    return b64


# ═══════════════════════════════════════════════════════════════════════════════
#  4. POST TO NIGHTION BACKEND  /api/vision
# ═══════════════════════════════════════════════════════════════════════════════

def call_vision_endpoint(image_b64: str, prompt: str = "") -> dict:
    """
    POST the captured image to Nightion's /api/vision endpoint.
    The backend handles both gemma4 passes internally.

    Returns: {"success": bool, "answer": str, "error": str|None}
    """
    if not prompt:
        prompt = (
            "You are looking at a screenshot the user selected. "
            "Your job is to produce the EXACT text the user needs to type into a text field. "
            "\n\nRules:\n"
            "- If the screenshot shows a QUESTION (exam, quiz, form field, homework, etc.), "
            "write the COMPLETE answer the user should type.\n"
            "- If it shows CODE with an error or incomplete code, write the CORRECTED or COMPLETED code.\n"
            "- If it shows a fill-in-the-blank or short-answer field, write ONLY what goes in that field.\n"
            "- If it shows a multiple-choice question, write ONLY the correct option letter and answer.\n"
            "\nCRITICAL: Output ONLY the answer text itself. "
            "Do NOT include explanations, commentary, labels, or markdown formatting. "
            "Do NOT say 'The answer is...' or 'Here is...'. "
            "The user will paste/type your output directly into a text field, "
            "so output ONLY what should appear in that field."
        )

    # ── Validate image payload before sending ────────────────────────────
    if not image_b64 or len(image_b64) < 100:
        log.error(f"Image payload too small ({len(image_b64) if image_b64 else 0} chars) — likely corrupt")
        return {"success": False, "answer": "", "error": "Image payload too small or empty"}

    # Check base64 is valid
    try:
        raw_bytes = base64.b64decode(image_b64)
        log.info(f"Image payload: {len(image_b64)} chars base64 → {len(raw_bytes)} bytes raw ({len(raw_bytes)//1024} KB)")
    except Exception as e:
        log.error(f"Image base64 is invalid: {e}")
        return {"success": False, "answer": "", "error": f"Invalid image encoding: {e}"}

    payload = json.dumps({
        "image": image_b64,
        "prompt": prompt,
    }).encode("utf-8")

    log.info(f"Sending to {VISION_ENDPOINT} — payload: {len(payload)} bytes")

    req = urllib.request.Request(
        VISION_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            log.info(f"Vision response: success={data.get('success')}, "
                     f"answer_len={len(data.get('answer', ''))}, "
                     f"pass1_len={len(data.get('pass1', ''))}")
            return data
    except urllib.error.URLError as e:
        log.error(f"Backend unreachable: {e}")
        return {"success": False, "answer": "", "error": f"Backend unreachable: {e}"}
    except Exception as e:
        log.error(f"Vision call failed: {e}")
        return {"success": False, "answer": "", "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
#  5. CLEAN ANSWER TEXT
# ═══════════════════════════════════════════════════════════════════════════════

def _strip_markdown(text: str) -> str:
    """
    Remove common markdown formatting so the typed output is clean text.
    Strips code fences, headers, bold/italic markers, etc.
    """
    # Remove code fences: ```lang\n...``` → just the code inside
    text = re.sub(r'```\w*\n?', '', text)

    # Remove inline code backticks
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove bold/italic markers
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove header markers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove common preambles the model might sneak in
    preamble_patterns = [
        r'^(?:The answer is|Here is|Here\'s|Answer:|Solution:|Output:)\s*:?\s*',
        r'^(?:The correct answer is|The result is)\s*:?\s*',
    ]
    for pattern in preamble_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)

    # Collapse multiple blank lines into one
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  6. CLICK-TO-TYPE (pynput listener → pynput keyboard typing)
# ═══════════════════════════════════════════════════════════════════════════════

def wait_for_click_and_type(text: str, timeout: int = 120):
    """
    Arm a pynput mouse listener. On next click anywhere, type the text
    at human-like speed using pynput's keyboard Controller (~0.04-0.07s
    per character with slight random variance).
    """
    from pynput.keyboard import Controller as KbController, Key
    from pynput.mouse import Listener as MouseListener

    click_event = threading.Event()

    def on_click(x, y, button, pressed):
        if pressed:
            click_event.set()
            return False  # Stop listener

    listener = MouseListener(on_click=on_click)
    listener.start()

    log.info("Waiting for click to start typing...")

    # Wait for click or timeout
    clicked = click_event.wait(timeout=timeout)
    listener.stop()

    if not clicked:
        log.warning("Timeout — no click detected")
        _show_toast("⏰ Timeout — no click detected", duration=3, fg="#ff6b6b")
        return

    # Small delay to let the click register and cursor to be placed
    time.sleep(0.35)

    # ── Clean the text before typing ─────────────────────────────────────
    text = _strip_markdown(text)
    if not text:
        log.warning("Answer is empty after cleaning")
        _show_toast("⚠ Empty answer after cleanup", duration=3, fg="#ffcc00")
        return

    # Type at human-like speed using pynput (handles all Unicode)
    log.info(f"Typing {len(text)} characters...")
    _show_toast(f"⌨ Typing {len(text)} chars...", duration=1.5, fg="#00d4ff")

    kb = KbController()

    for char in text:
        delay = random.uniform(0.04, 0.07)
        try:
            if char == '\n':
                kb.press(Key.enter)
                kb.release(Key.enter)
                delay += random.uniform(0.06, 0.10)  # Extra pause after newline
            elif char == '\t':
                kb.press(Key.tab)
                kb.release(Key.tab)
            else:
                # pynput's type() handles ASCII + Unicode correctly
                kb.type(char)
        except Exception as e:
            log.warning(f"Could not type char {repr(char)}: {e}")
        time.sleep(delay)

    log.info("Typing complete!")
    _show_toast("✅ Done!", duration=1.5, fg="#00ff88")


# ═══════════════════════════════════════════════════════════════════════════════
#  6. MAIN PIPELINE: Hotkey → Overlay → Capture → Vision → Click → Type
# ═══════════════════════════════════════════════════════════════════════════════

def _run_pipeline():
    """
    Full Smart Cursor pipeline. Called when Ctrl+Shift+0 is pressed.
    Runs the overlay on the main thread via tkinter, everything else
    in the current thread.
    """
    global _is_active

    with _active_lock:
        if _is_active:
            log.warning("Pipeline already active, ignoring hotkey")
            return
        _is_active = True

    try:
        log.info("━━━ Smart Cursor activated ━━━")

        # Step 1: Area selector overlay
        _show_toast("🎯 Select a region...", duration=1.5, fg="#ffcc00")
        time.sleep(0.3)  # Let toast appear

        region = select_screen_region()
        if region is None:
            log.info("Selection cancelled")
            _show_toast("❌ Cancelled", duration=1.5, fg="#ff6b6b")
            return

        log.info(f"Selected region: {region}")

        # Step 2: Wait for overlay to fully clear from DWM compositor,
        # then capture with mss
        _show_toast("📸 Capturing...", duration=1.5, fg="#00d4ff")
        time.sleep(0.5)  # ← CRITICAL: let tkinter overlay fully disappear from DWM
        image_b64 = capture_region(region)

        # Validate capture before sending
        if not image_b64 or len(image_b64) < 500:
            log.error(f"Capture too small: {len(image_b64) if image_b64 else 0} chars")
            _show_toast("❌ Capture failed — image too small", duration=4, fg="#ff6b6b")
            return

        # Step 3: Send to Nightion backend
        _show_toast("🧠 Analyzing screenshot...", duration=8, fg="#c084fc")
        result = call_vision_endpoint(image_b64)

        if not result.get("success"):
            error = result.get("error", "Unknown error")
            log.error(f"Vision failed: {error}")
            print(f"[SmartCursor] ❌ Vision failed: {error}")
            _show_toast(f"❌ Failed: {error[:80]}", duration=6, fg="#ff6b6b")
            return

        answer = result.get("answer", "").strip()
        pass1 = result.get("pass1", "").strip()

        if not answer:
            log.warning("Empty answer from backend")
            # Fall back to pass1 if available
            if pass1:
                log.info(f"Using pass1 as fallback ({len(pass1)} chars)")
                answer = pass1
            else:
                print("[SmartCursor] ⚠ Empty answer from backend")
                _show_toast("⚠ Empty answer from model", duration=5, fg="#ffcc00")
                return

        log.info(f"Answer received ({len(answer)} chars): {answer[:120]}...")
        print(f"[SmartCursor] ✓ Answer ({len(answer)} chars): {answer[:200]}")

        # Step 4: Arm click listener
        _show_toast("✦ Click any text field to type the answer", duration=15, fg="#00ff88")
        wait_for_click_and_type(answer)

    except Exception as e:
        log.error(f"Pipeline error: {e}", exc_info=True)
        _show_toast(f"❌ Error: {str(e)[:60]}", duration=4, fg="#ff6b6b")
    finally:
        with _active_lock:
            _is_active = False


def _on_hotkey():
    """
    Hotkey callback — runs the pipeline in a new thread so the keyboard
    hook isn't blocked. But the tkinter overlay needs the main thread,
    so we post to it.
    """
    # Run pipeline directly — keyboard library calls this from its own thread
    # and tkinter will create its own mainloop
    _run_pipeline()


# ═══════════════════════════════════════════════════════════════════════════════
#  7. ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """
    Start the Smart Cursor background listener.
    Registers global hotkey and blocks forever.
    """
    import keyboard

    log.info("╔══════════════════════════════════════════════════╗")
    log.info("║     Nightion Smart Cursor — Background Mode     ║")
    log.info(f"║     Hotkey: {HOTKEY:<37s} ║")
    log.info(f"║     Backend: {NIGHTION_BACKEND:<36s} ║")
    log.info("╚══════════════════════════════════════════════════╝")

    keyboard.add_hotkey(HOTKEY, _on_hotkey, suppress=True)
    _show_toast("✦ Smart Cursor active — Ctrl+Shift+0", duration=3, fg="#00ff88")

    log.info(f"Global hotkey '{HOTKEY}' registered. Waiting...")

    # Block forever — the keyboard hook runs in a background thread
    try:
        keyboard.wait()  # Blocks until keyboard.unhook_all() or process killed
    except KeyboardInterrupt:
        log.info("Smart Cursor shutting down...")


if __name__ == "__main__":
    main()
