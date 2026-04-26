import pytest
import sqlite3
import os
import asyncio
from schemas import AgentRequest, IntentEnum, ToolResult, StatusEnum, VerificationDecision
from tool_router import ToolRouter, RouterConfig
from orchestrator import Orchestrator
from memory_core import MemoryCore
from retrieval_governor import RetrievalGovernor
from verifier import Verifier

@pytest.mark.asyncio
async def test_memory_governance_injection_filtering():
    """
    Test Case: Automated search snippets should be in DB but NOT in reasoning context.
    """
    db_path = "test_memory_hardened.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    memory = MemoryCore(db_path=db_path)
    governor = RetrievalGovernor(memory)
    
    # 1. Store automated search facts (inject=0)
    memory.add_verified_fact(
        trace_id="trace-001",
        source="https://example.com/search",
        fact="Binary search is O(log n)",
        confidence=0.9,
        inject=0
    )
    
    memory.add_verified_fact(
        trace_id="trace-001",
        source="https://example.com/docs",
        fact="Python uses 'def' for functions",
        confidence=0.9,
        inject=0
    )
    
    # 2. Store a manual/important fact (inject=1, default)
    memory.add_verified_fact(
        trace_id="trace-002",
        source="user_instruction",
        fact="Always use 4 spaces for indentation",
        confidence=1.0,
        inject=1
    )
    
    # 3. Verify RetrievalGovernor output
    # It should ONLY return the injected fact
    payload = governor.construct_planner_payload(session_id="test_session")
    verified_facts = payload["verified_facts"]
    
    assert len(verified_facts) == 1, "Only 1 fact should be in the reasoning context"
    assert "Always use 4 spaces" in verified_facts[0]
    assert not any("Binary search" in f for f in verified_facts), "Search snippets should NOT be injected"
    
    # 4. Verify Raw DB contains ALL 3 facts
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    conn.close()
    
    assert count == 3, "Database should contain all 3 facts for audit trail"
    
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.mark.asyncio
async def test_semantic_reroute_circuit_breaker():
    """
    Test Case: Orchestrator should cap reroutes to prevent infinite loops.
    """
    # This involves mocking the Verifier to always return a trigger_reroute
    # and checking if the loop terminates.
    
    # 1. Mock Verifier to always reroute
    class InfiniteRerouteVerifier(Verifier):
        async def verify(self, query, intent, tool_res, trace_id):
            return pytest.importorskip("schemas").VerificationResult(
                trace_id=trace_id,
                decision=VerificationDecision.FAIL,
                status=StatusEnum.FAILED,
                confidence=1.0,
                reason="CONSTANT_MISMATCH",
                suggested_fix="Reroute suggested.",
                trigger_reroute=True,
                suggested_intent=IntentEnum.CODE if intent == IntentEnum.SEARCH else IntentEnum.SEARCH,
                severity="high"
            )

    # 2. Mock Orchestrator to use our Verifier
    from unittest.mock import patch, MagicMock, AsyncMock
    
    router = ToolRouter(config=RouterConfig())
    orchestrator = Orchestrator(router=router, max_retries=5)
    
    # Mock _run_tool to always return a search result
    with patch.object(Orchestrator, "_run_tool", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = ToolResult(
            trace_id="trace-reroute",
            tool_name="search",
            status=StatusEnum.OK,
            output="Found 5 Top Sources...",
            execution_time_ms=10,
            metadata={}
        )
        # Mock _verify_output to use InfiniteRerouteVerifier
        with patch.object(Orchestrator, "_verify_output", new_callable=AsyncMock) as mock_verify:
            # We want it to fail and reroute
            async def mock_verify_logic(q, i, tr):
                return await InfiniteRerouteVerifier().verify(q, i, tr, "trace-reroute")
            
            mock_verify.side_effect = mock_verify_logic
            
            # Mock UI feedback to track calls
            ui_cb = MagicMock(return_value=asyncio.Future())
            ui_cb.return_value.set_result(None)
            
            request = AgentRequest(query="write code", trace_id="trace-reroute")
            response = await orchestrator.execute_task(request, ui_feedback_cb=ui_cb)
            
            # 3. Assertions
            # The circuit breaker (max_reroutes=2) should stop it.
            # Reroute count 0 -> Reroute 1 -> Reroute 2 -> HALT.
            halt_calls = [call for call in ui_cb.call_args_list if "🛑 Reroute Limit Reached" in call[0][0]]
            assert len(halt_calls) == 1, "Reroute limit should have been reached and logged to UI"
            assert response.status in [StatusEnum.FAILED, StatusEnum.BLOCKED]

if __name__ == "__main__":
    asyncio.run(test_memory_governance_injection_filtering())
    asyncio.run(test_semantic_reroute_circuit_breaker())
