"""
Nightion Code Runner
Safe Python code execution in a subprocess sandbox with timeout.
"""

import subprocess
import sys
import tempfile
import os
import time


def run_python(code: str, timeout: int = 10) -> dict:
    """
    Execute Python code safely in a subprocess.
    Returns: {"stdout": str, "stderr": str, "success": bool, "duration": float}
    """
    # Write code to a temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        tmp_path = f.name

    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tempfile.gettempdir()
        )
        duration = time.time() - start
        return {
            "stdout": result.stdout[:4000] if result.stdout else "",
            "stderr": result.stderr[:2000] if result.stderr else "",
            "success": result.returncode == 0,
            "duration": round(duration, 3)
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"⏱️ Execution timed out after {timeout} seconds.",
            "success": False,
            "duration": timeout
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"Execution error: {str(e)}",
            "success": False,
            "duration": 0
        }
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass
