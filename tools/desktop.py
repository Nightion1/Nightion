from schemas import ToolResult, StatusEnum
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from guards import evaluate_action, ActionRisk
import time

class DesktopTool:
    """
    Agent tool adapter for local OS and Application control.
    Mandates traffic through `guards.py` before executing any local actions.
    """
    def __init__(self):
        self.tool_name = "app_control"

    async def execute(self, action: str, target: str, payload: dict, trace_id: str) -> ToolResult:
        start = time.time()
        try:
            # 1. Absolute Authority Safety Check
            guard = evaluate_action(action, target, payload)
            
            if not guard.allowed:
                return ToolResult(
                    trace_id=trace_id,
                    tool_name=self.tool_name,
                    status=StatusEnum.BLOCKED,
                    output=None,
                    error=f"Safety Guard BLOCKED Action: {guard.reason}",
                    requires_confirmation=(guard.risk_level == ActionRisk.CRITICAL),
                    execution_time_ms=int((time.time() - start) * 1000),
                    metadata={"target": target, "action": action, "risk": guard.risk_level.value}
                )

            # 2. Safe Execution Payload
            # TODO: Add local OS bindings (e.g., pyautogui or wmi)
            return ToolResult(
                trace_id=trace_id,
                tool_name=self.tool_name,
                status=StatusEnum.OK,
                output=f"Successfully executed SAFE action: {action} on {target}.",
                execution_time_ms=int((time.time() - start) * 1000)
            )

        except Exception as e:
            return ToolResult(
                trace_id=trace_id,
                tool_name=self.tool_name,
                status=StatusEnum.FAILED,
                output=None,
                error=f"App control subsystem failure: {str(e)}",
                execution_time_ms=int((time.time() - start) * 1000)
            )
