import subprocess
import tempfile
import os
import time

from schemas import ToolResult, StatusEnum

class Sandbox:
    """
    Isolated and deterministic Python execution environment.
    Provides the foundation of truth for code dry-runs and execution.
    """
    def __init__(self, timeout: int = 3):
        self.timeout = timeout
        self.blocked_imports = ["os", "sys", "subprocess", "shutil", "socket", "pathlib"]

    def _scan_for_malicious_imports(self, code: str) -> bool:
        """ Returns true if blocked imports are detected """
        for block in self.blocked_imports:
            # Naive safety check for MVP blocking static and dynamic imports
            if (f"import {block}" in code or 
                f"from {block}" in code or 
                f"__import__('{block}')" in code or 
                f'__import__("{block}")' in code):
                return True
        return False

    def execute_python(self, code: str, trace_id: str) -> ToolResult:
        start = time.time()
        
        # 1. Security Check
        if self._scan_for_malicious_imports(code):
            return ToolResult(
                trace_id=trace_id,
                tool_name="sandbox_python",
                status=StatusEnum.BLOCKED,
                output=None,
                error="Security Exception: Usage of restricted modules (os, sys, subprocess, etc.) is blocked in the sandbox.",
                execution_time_ms=int((time.time() - start) * 1000),
            )

        # 2. Execution Wrapper
        # Wraps the raw code inside a def layer to prevent scope leak and enforce simple run
        wrapped_code = f"def __sandbox_run():\n"
        wrapped_code += "\n".join([f"    {line}" for line in code.split("\n")])
        wrapped_code += "\n\nif __name__ == '__main__':\n    __sandbox_run()\n"

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding='utf-8') as tmp:
                # The code might be self-contained so wrapping it could break standard defs.
                # For MVP stability based on the spec, we will execute raw code safely.
                # Reverting wrapper for raw code execution to ensure classes/imports resolve properly cleanly.
                pass
            
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding='utf-8') as tmp:
                tmp.write(code)
                tmp_path = tmp.name

            # 3. Subprocess Execution
            result = subprocess.run(
                ["python", tmp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            execution_time = int((time.time() - start) * 1000)

            # 4. Result Parsing
            if result.returncode != 0:
                return ToolResult(
                    trace_id=trace_id,
                    tool_name="sandbox_python",
                    status=StatusEnum.FAILED,
                    output=None,
                    error=str(result.stderr or "").strip()[:1000],  # Cap error length
                    execution_time_ms=execution_time,
                )

            return ToolResult(
                trace_id=trace_id,
                tool_name="sandbox_python",
                status=StatusEnum.OK,
                output=str(result.stdout or "").strip(),
                error=None,
                execution_time_ms=execution_time,
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                trace_id=trace_id,
                tool_name="sandbox_python",
                status=StatusEnum.FAILED,
                output=None,
                error=f"Execution timed out after {self.timeout} seconds",
                execution_time_ms=int((time.time() - start) * 1000),
            )

        except Exception as e:
            return ToolResult(
                trace_id=trace_id,
                tool_name="sandbox_python",
                status=StatusEnum.FAILED,
                output=None,
                error=str(e),
                execution_time_ms=int((time.time() - start) * 1000),
            )

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except:
                    pass
