"""
see_and_code.py — Nightion See & Code Pipeline
Screen capture → multimodal AI code generation → human-like auto-typing.

Functions:
    capture_screen()          — Screenshot via pyautogui, returns base64 PNG
    generate_code_from_image  — Vision model call → extract code block
    type_code_humanlike()     — pynput character-by-character with realistic timing
"""

import base64
import io
import json
import logging
import random
import re
import threading
import time
import urllib.request
import urllib.error
from typing import Optional, Tuple

log = logging.getLogger("nightion.see_and_code")

# ── Global cancel event — set from any thread to stop typing ──────────────────
_cancel_event = threading.Event()


def cancel_typing():
    """Signal the typing loop to stop immediately."""
    _cancel_event.set()


def reset_cancel():
    """Clear the cancel signal for a new session."""
    _cancel_event.clear()


# ═══════════════════════════════════════════════════════════════════════════════
#  1. SCREEN CAPTURE
# ═══════════════════════════════════════════════════════════════════════════════

def _switch_to_previous_window():
    """
    Switch to the previous window/tab using Alt+Tab so we capture
    the target application (e.g. CodeTantra) instead of the Nightion tab.
    """
    import pyautogui
    pyautogui.FAILSAFE = True
    log.info("[See&Code] Switching to previous window via Alt+Tab...")
    pyautogui.hotkey('alt', 'tab')
    time.sleep(1.0)  # Wait for window switch animation to complete


def _switch_back_to_nightion():
    """
    Switch back to the Nightion window after capturing.
    """
    import pyautogui
    pyautogui.FAILSAFE = True
    log.info("[See&Code] Switching back to Nightion via Alt+Tab...")
    pyautogui.hotkey('alt', 'tab')
    time.sleep(0.5)


def capture_screen(max_width: int = 1280, switch_window: bool = True) -> Tuple[str, Tuple[int, int]]:
    """
    Take a screenshot of the entire screen, resize if needed,
    and return (base64_png_string, (width, height)).

    If switch_window is True, Alt+Tab to the previous window first
    so we capture the target app (e.g. CodeTantra) instead of Nightion.
    After capturing, Alt+Tab back to Nightion.
    """
    import pyautogui
    from PIL import Image

    pyautogui.FAILSAFE = True

    # Switch to the target window before capturing
    if switch_window:
        _switch_to_previous_window()

    screenshot = pyautogui.screenshot()
    w, h = screenshot.size
    log.info(f"[See&Code] Captured screenshot: {w}x{h}")

    # Switch back to Nightion after capturing
    if switch_window:
        _switch_back_to_nightion()

    if w > max_width:
        ratio = max_width / w
        screenshot = screenshot.resize((max_width, int(h * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    screenshot.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

    return img_b64, screenshot.size


# ═══════════════════════════════════════════════════════════════════════════════
#  2. MULTIMODAL CODE GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

# Lang name normalization for prompts
_LANG_DISPLAY = {
    "python": "Python",
    "cpp": "C++",
    "c": "C",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "csharp": "C#",
    "go": "Go",
    "rust": "Rust",
    "sql": "SQL",
}

# Code fence markers for each language
_LANG_FENCE = {
    "python": "python",
    "cpp": "cpp",
    "c": "c",
    "java": "java",
    "javascript": "javascript",
    "typescript": "typescript",
    "csharp": "csharp",
    "go": "go",
    "rust": "rust",
    "sql": "sql",
}


def _strip_thinking_tags(text: str) -> str:
    """
    Remove <think>...</think> blocks that gemma4 may include in its response.
    Also removes any stray opening/closing think tags.
    """
    # Remove complete think blocks
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', text)
    # Remove stray tags
    cleaned = re.sub(r'</?think>', '', cleaned)
    return cleaned.strip()


def _try_vision_model(image_b64: str, language: str, model: str = "gemma4") -> Optional[str]:
    """
    Attempt a multimodal generate call to the given Ollama model.
    Returns the raw response text, or None on failure.
    """
    lang_display = _LANG_DISPLAY.get(language, language.capitalize())
    fence = _LANG_FENCE.get(language, language)

    prompt = (
        f"This screenshot shows a programming problem or coding question. "
        f"Read the problem statement carefully from the screenshot. "
        f"Write a COMPLETE, WORKING solution in {lang_display}. "
        f"IMPORTANT RULES:\n"
        f"- Output ONLY the code inside a ```{fence} code block\n"
        f"- Do NOT include any explanation, description, or commentary\n"
        f"- Do NOT describe the problem — just solve it\n"
        f"- Do NOT write helper text like 'Here is the solution' or 'This code does...'\n"
        f"- Include ALL necessary imports, function definitions, and boilerplate\n"
        f"- The code must be ready to copy-paste and run\n"
    )

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }).encode()

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            raw = result.get("response", "")
            # Strip any thinking tags that may have leaked through
            return _strip_thinking_tags(raw)
    except Exception as e:
        log.warning(f"[See&Code] Vision model '{model}' failed: {e}")
        return None


def _extract_code_block(raw_text: str, language: str) -> str:
    """
    Extract the first fenced code block from model output.
    Tries language-specific fence first, then generic.
    If NO code fence is found, returns the raw output directly as-is
    so it can be used for writing without any filtering.
    """
    # First, strip any thinking tags
    cleaned_text = _strip_thinking_tags(raw_text)

    fence = _LANG_FENCE.get(language, language)

    # Try specific language fence
    pattern = rf"```{re.escape(fence)}\s*\n([\s\S]*?)```"
    match = re.search(pattern, cleaned_text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Try any fenced block
    match = re.search(r"```\w*\s*\n([\s\S]*?)```", cleaned_text)
    if match:
        return match.group(1).strip()

    # Try fence without language tag  (```\n...```)
    match = re.search(r"```\s*\n([\s\S]*?)```", cleaned_text)
    if match:
        return match.group(1).strip()

    # No code fences found — use the raw output directly through gemma4 for writing
    log.info("[See&Code] No code block found, using raw output directly for writing")
    return cleaned_text.strip()


def generate_code_from_image(
    image_b64: str,
    language: str = "python",
    primary_model: str = "gemma4",
    fallback_model: str = "gemma4",
) -> dict:
    """
    Send screenshot to gemma4 vision model and extract code.
    Uses ONLY gemma4 — no llava or other models.

    Strategy:
        1. Try gemma4 with multimodal vision (concise prompt)
        2. If code is too short, retry gemma4 with a more detailed prompt

    Returns:
        {"success": bool, "code": str, "language": str, "analysis": str, "model_used": str}
    """
    lang_display = _LANG_DISPLAY.get(language, language.capitalize())
    fence = _LANG_FENCE.get(language, language)

    # ── Attempt 1: Direct vision with gemma4 ──────────────────────────────
    raw = _try_vision_model(image_b64, language, primary_model)
    if raw and raw.strip():
        code = _extract_code_block(raw, language)
        if code and len(code) > 10:
            log.info(f"[See&Code] Direct vision success with {primary_model}")
            return {
                "success": True,
                "code": code,
                "language": language,
                "analysis": f"Solved via {primary_model} vision",
                "model_used": primary_model,
            }

    # ── Attempt 2: Retry gemma4 with a more detailed/explicit prompt ──────
    log.info(f"[See&Code] First attempt insufficient, retrying {primary_model} with detailed prompt")

    retry_prompt = (
        f"Look at this screenshot very carefully. It contains a programming question, problem, or coding task. "
        f"Read EVERY word on the screen including constraints, input/output format, and examples. "
        f"Then write a COMPLETE, WORKING solution in {lang_display}. "
        f"CRITICAL: Your response must contain ONLY the code inside a ```{fence} code block. "
        f"Do NOT include ANY text outside the code block — no explanations, no descriptions, no 'Here is...' text. "
        f"Include ALL necessary imports, function definitions, and a main section if needed. "
        f"Do NOT skip any part of the solution. ONLY CODE."
    )

    try:
        retry_payload = json.dumps({
            "model": primary_model,
            "prompt": retry_prompt,
            "images": [image_b64],
            "stream": False,
            "think": False,
            "options": {"temperature": 0.3, "num_predict": 3000},
        }).encode()

        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=retry_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            raw_retry = _strip_thinking_tags(result.get("response", ""))
    except Exception as e:
        log.warning(f"[See&Code] Retry with {primary_model} failed: {e}")
        return {
            "success": False,
            "code": "",
            "language": language,
            "analysis": f"gemma4 vision failed: {e}",
            "model_used": primary_model,
        }

    if raw_retry and raw_retry.strip():
        code = _extract_code_block(raw_retry, language)
        if code and len(code) > 10:
            log.info(f"[See&Code] Retry vision success with {primary_model}")
            return {
                "success": True,
                "code": code,
                "language": language,
                "analysis": f"Solved via {primary_model} vision (retry)",
                "model_used": primary_model,
            }

    return {
        "success": False,
        "code": raw_retry.strip() if raw_retry else (raw.strip() if raw else ""),
        "language": language,
        "analysis": "gemma4 could not generate sufficient code from the screenshot",
        "model_used": primary_model,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  3. HUMAN-LIKE TYPING
# ═══════════════════════════════════════════════════════════════════════════════

# Characters that should NEVER be typo'd
_PROTECTED_CHARS = set(";{}[]()=<>:,.'\"\\|/!@#$%^&*+-~`")

# Language keywords that should never be typo'd mid-word
_PROTECTED_KEYWORDS = {
    "def", "class", "return", "import", "from", "if", "else", "elif",
    "for", "while", "try", "except", "finally", "with", "as", "in",
    "not", "and", "or", "is", "None", "True", "False", "print",
    "int", "str", "float", "list", "dict", "set", "tuple", "len",
    "range", "self", "void", "public", "private", "static", "final",
    "include", "using", "namespace", "template", "const", "auto",
    "function", "var", "let", "const", "async", "await", "yield",
    "fn", "pub", "mut", "impl", "struct", "enum", "match",
}

# Wrong-key neighbors on QWERTY for typo simulation
_QWERTY_NEIGHBORS = {
    'a': 'sq', 'b': 'vn', 'c': 'xv', 'd': 'sf', 'e': 'wr',
    'f': 'dg', 'g': 'fh', 'h': 'gj', 'i': 'uo', 'j': 'hk',
    'k': 'jl', 'l': 'k;', 'm': 'n,', 'n': 'bm', 'o': 'ip',
    'p': 'o[', 'q': 'w', 'r': 'et', 's': 'ad', 't': 'ry',
    'u': 'yi', 'v': 'cb', 'w': 'qe', 'x': 'zc', 'y': 'tu',
    'z': 'x',
}


def _get_typo_char(correct: str) -> str:
    """Return a plausible wrong character for a typo."""
    lower = correct.lower()
    neighbors = _QWERTY_NEIGHBORS.get(lower, "")
    if neighbors:
        wrong = random.choice(neighbors)
        return wrong.upper() if correct.isupper() else wrong
    return correct  # Can't typo this char


def _is_in_keyword(code: str, pos: int) -> bool:
    """Check if char at position is part of a protected keyword."""
    # Extract the word containing this position
    start = pos
    while start > 0 and code[start - 1].isalnum():
        start -= 1
    end = pos
    while end < len(code) and code[end].isalnum():
        end += 1
    word = code[start:end]
    return word in _PROTECTED_KEYWORDS


def _strip_indentation_for_editor(code: str) -> str:
    """
    Strip leading whitespace from each line of the code.

    Online code editors (OnlineGDB, CodeTantra, HackerRank, etc.)
    auto-indent when you press Enter after '{', '(', ':', etc.
    If we ALSO type the source code's indentation, the result is
    double-indented code that takes up way too much horizontal space.

    This function removes all leading spaces/tabs from each line,
    letting the target editor's auto-indent handle proper formatting.
    """
    lines = code.split('\n')
    stripped_lines = []
    for line in lines:
        stripped_lines.append(line.lstrip(' \t'))
    return '\n'.join(stripped_lines)


def type_code_humanlike(code: str, strip_indent: bool = True) -> dict:
    """
    Type code character-by-character into whatever application is focused,
    using human-like timing and occasional realistic typos.

    Args:
        code: The code string to type.
        strip_indent: If True (default), strip leading whitespace from each
                      line so online editors' auto-indent doesn't double up.

    Returns: {"success": bool, "chars_typed": int, "method": str, "error": str|None}
    """
    reset_cancel()

    if not code or not code.strip():
        return {"success": False, "chars_typed": 0, "method": "humanlike", "error": "No code provided"}

    # Pre-process: strip indentation for online editor compatibility
    if strip_indent:
        code = _strip_indentation_for_editor(code)

    try:
        from pynput.keyboard import Controller as KbController, Key
        import pyautogui
    except ImportError as e:
        return {"success": False, "chars_typed": 0, "method": "humanlike", "error": f"Missing dependency: {e}"}

    kb = KbController()
    chars_typed = 0
    chars_since_last_typo = 0
    burst_mode = False
    burst_remaining = 0

    # Special character mapping for pyautogui
    _SPECIAL_VIA_PYAUTOGUI = set("{}[]()@#$%^&*~`|\\<>")

    try:
        for i, char in enumerate(code):
            # ── Check cancel ──────────────────────────────────────────────
            if _cancel_event.is_set():
                log.info(f"[See&Code] Typing cancelled at char {i}/{len(code)}")
                return {
                    "success": True,
                    "chars_typed": chars_typed,
                    "method": "humanlike_cancelled",
                    "error": None,
                }

            # ── Determine delay ───────────────────────────────────────────
            if burst_mode and burst_remaining > 0:
                delay = random.uniform(0.010, 0.020)
                burst_remaining -= 1
                if burst_remaining <= 0:
                    burst_mode = False
                    time.sleep(random.uniform(0.100, 0.140))  # Post-burst pause
            else:
                # Base delay: 35-70ms
                delay = random.uniform(0.035, 0.070)

                # Extra delays for structural characters
                if char == '\n':
                    delay += random.uniform(0.080, 0.120)
                elif char in ('{', '('):
                    delay += random.uniform(0.040, 0.060)
                elif char == '\t':
                    delay += random.uniform(0.020, 0.040)

                # Random burst initiation (~8% chance per char)
                if random.random() < 0.08:
                    burst_mode = True
                    burst_remaining = random.randint(5, 8)

            # ── Typo simulation ───────────────────────────────────────────
            chars_since_last_typo += 1
            should_typo = (
                chars_since_last_typo >= 50 and
                random.random() < 0.04 and
                char.isalpha() and
                char not in _PROTECTED_CHARS and
                not _is_in_keyword(code, i)
            )

            if should_typo:
                # Type wrong char → pause → backspace → correct char
                wrong = _get_typo_char(char)
                if wrong != char:
                    kb.type(wrong)
                    time.sleep(random.uniform(0.080, 0.150))
                    kb.press(Key.backspace)
                    kb.release(Key.backspace)
                    time.sleep(random.uniform(0.050, 0.100))
                    chars_since_last_typo = 0

            # ── Type the character ────────────────────────────────────────
            time.sleep(delay)

            if char == '\n':
                kb.press(Key.enter)
                kb.release(Key.enter)
            elif char == '\t':
                kb.press(Key.tab)
                kb.release(Key.tab)
            elif char in _SPECIAL_VIA_PYAUTOGUI:
                # Use pyautogui for special characters (handles shift states)
                try:
                    pyautogui.write(char, interval=0)
                except Exception:
                    kb.type(char)
            else:
                kb.type(char)

            chars_typed += 1

        return {
            "success": True,
            "chars_typed": chars_typed,
            "method": "humanlike",
            "error": None,
        }

    except Exception as e:
        log.error(f"[See&Code] Typing error at char {chars_typed}: {e}")
        return {
            "success": False,
            "chars_typed": chars_typed,
            "method": "humanlike",
            "error": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  4. EXTERNAL CLICK LISTENER (waits for user to click outside Nightion)
# ═══════════════════════════════════════════════════════════════════════════════

def wait_for_external_click_then_type(code: str, timeout: int = 60) -> dict:
    """
    Start a pynput global mouse listener. Wait for ANY click (outside or inside),
    then begin human-like typing of the code.

    The idea: user clicks in their target editor (Notepad, VS Code, etc.)
    to place the cursor, then this function starts typing.

    Args:
        code: The code string to type
        timeout: Max seconds to wait for a click before giving up

    Returns: typing result dict
    """
    reset_cancel()
    click_detected = threading.Event()

    def on_click(x, y, button, pressed):
        if pressed:
            click_detected.set()
            return False  # Stop listener

    try:
        from pynput.mouse import Listener as MouseListener
    except ImportError:
        return {"success": False, "chars_typed": 0, "method": "humanlike", "error": "pynput not installed"}

    # Start listening for mouse clicks
    listener = MouseListener(on_click=on_click)
    listener.start()

    log.info("[See&Code] Waiting for external click to start typing...")

    # Wait for click or cancel or timeout
    waited = 0
    while waited < timeout:
        if _cancel_event.is_set():
            listener.stop()
            return {"success": False, "chars_typed": 0, "method": "humanlike_cancelled", "error": "Cancelled while waiting"}
        if click_detected.wait(timeout=0.5):
            break
        waited += 0.5

    listener.stop()

    if not click_detected.is_set():
        return {"success": False, "chars_typed": 0, "method": "humanlike", "error": "Timeout waiting for click"}

    # Small delay to let the click register in the target app
    time.sleep(0.3)

    # Now type the code
    return type_code_humanlike(code)
