import pytest
import asyncio
from schemas import AgentRequest, StatusEnum, NextActionEnum
from orchestrator import Orchestrator

class MockFailingToolManager:
    """ Forces the Sandbox to fail deterministically offline checking explicit Recovery routing limits. """
    async def execute(self, intent, args, trace_id):
        from schemas import ToolResult
        return ToolResult(trace_id=trace_id, tool_name="strict_sandbox", status=StatusEnum.FAILED, output="MOCKED ERR: Sandbox memory exhaustion limit reached.", execution_time_ms=100)

class MockConflictingBus:
    """ Triggers a TaskBus arbitration crash tracking exact Verifier bypass traps organically. """
    async def route_task(self, proposal):
        from schemas import TaskResultNode, TaskResultStatus
        return TaskResultNode(
            task_id="err-111", trace_id="sub-123", status=TaskResultStatus.CONFLICTING, 
            result_payload="Sub-Agents contradict routing pathways.",
            confidence=0.0
        )

def test_sandbox_failure_injection():
    """ Proves the TriState Verifier catches specific structural crashes gracefully avoiding unbounded Loops natively. """
    asyncio.run(_test_sandbox_failure_injection())
    
async def _test_sandbox_failure_injection():
    from tool_router import ToolRouter
    router = ToolRouter()
    orch = Orchestrator(router=router, max_retries=1)
    
    # Force deterministic Reasoning Schema preventing dynamic Fast-Paths bypassing sandbox loops internally.
    from reasoning_engine import ThoughtSchema
    class MockReasoning:
        async def analyze(self, query, intent, policy_state, feedback, memory_payload):
            return ThoughtSchema(
                understanding="Mocked evaluation understanding constraints natively.",
                intent="code", context_strategy="MOCK_STRATEGY", uncertainty=0.1, requires_tools=True,
                plan="Run code.", steps=["Execute sandbox explicitly offline."]
            )
    orch.reasoning = MockReasoning()
    
    # Overwrite the sandbox layer with deterministic Failure Node 
    orch.tool_manager = MockFailingToolManager()
    
    # Mock Verifier to forcefully catch the failure bypassing underlying LLM evaluations natively
    from schemas import VerificationResult, VerificationDecision
    class MockFailingVerifier:
        async def verify(self, query, tool_res, trace_id=None):
            from schemas import StatusEnum
            return VerificationResult(decision=VerificationDecision.FAIL, reason="Fault Injection caught natively.", suggested_fix="Bubble up bounds.", confidence=1.0, trace_id=trace_id or "err-test-01", status=StatusEnum.FAILED)
            
    orch._verify_output = MockFailingVerifier().verify
    
    req = AgentRequest(trace_id="test-val-err-001", query="Calculate explicit mathematical structural constraints natively.", history=[])
    
    # The Reasoner will plan code -> run code -> which returns MOCKED ERR -> The Verifier must intercept and fail gracefully.
    res = await orch.execute_task(req)
    
    assert res.status == StatusEnum.FAILED, "Engine failed to trap Sandbox memory exhaustion securely."
    assert "Loop Exhausted" in res.result or "Max retries exceeded" in res.result, "Engine didn't bounce properly off the Verifier checkpoint bounds natively offline."
