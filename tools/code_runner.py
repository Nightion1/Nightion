from sandbox import Sandbox
from schemas import ToolResult, StatusEnum
import time

class CodeRunnerTool:
    """
    Agent tool adapter for executing Python code securely.
    Acts as the bridging interface between the Orchestrator and the Sandbox.
    """
    
    def __init__(self, timeout: int = 5):
        self.sandbox = Sandbox(timeout=timeout)
        self.tool_name = "code_runner"

    async def execute(self, code: str, trace_id: str) -> ToolResult:
        """
        Executes the provided python code in the sandbox.
        """
        start = time.time()
        
        try:
            # Code Execution
            result: ToolResult = self.sandbox.execute_python(code=code, trace_id=trace_id)
            
            # Decorate the result with the active adapter identity and telemetry
            result.tool_name = self.tool_name
            result.metadata["code_runner"] = {"timeout_configured": self.sandbox.timeout}
            return result
            
        except Exception as e:
            return ToolResult(
                trace_id=trace_id,
                tool_name=self.tool_name,
                status=StatusEnum.FAILED,
                output=None,
                error=f"Tool adapter failure: {str(e)}",
                execution_time_ms=int((time.time() - start) * 1000)
            )
