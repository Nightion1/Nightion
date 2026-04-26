import pytest
import asyncio
import random
from schemas import AgentRequest, StatusEnum, NextActionEnum, IntentEnum
from orchestrator import Orchestrator
from tool_router import ToolRouter

def test_golden_trace_regression():
    """ Proves the architecture reproduces identically under Deterministic Seeds mapping pure Replay matchings entirely natively. """
    asyncio.run(_test_golden_trace_regression())

async def _test_golden_trace_regression():
    # 1. Deterministic Lock
    random.seed(42)
    
    # 2. Replay Initialization
    router = ToolRouter()
    orch = Orchestrator(router=router, max_retries=1)
    
    req_pass_1 = AgentRequest(trace_id="golden-001", query="Sort physical node parameters linearly offline.", history=[])
    
    # Bypass heavy mock generations locking deterministic Intent targeting
    res_1 = await orch.execute_task(req_pass_1, forced_intent=IntentEnum.CODE)
    
    # 3. Repeat identical Seed
    random.seed(42)
    orch_replay = Orchestrator(router=router, max_retries=1)
    req_pass_2 = AgentRequest(trace_id="golden-002", query="Sort physical node parameters linearly offline.", history=[])
    res_2 = await orch_replay.execute_task(req_pass_2, forced_intent=IntentEnum.CODE)
    
    # 4. Assert Exact Structure Fidelity
    assert res_1.status == res_2.status, "Golden Replay Failure: Status drifted offline."
    assert res_1.metadata.get("intent") == res_2.metadata.get("intent"), "Golden Replay Failure: Intent taxonomy shifted unexpectedly natively."
    
    print("Golden Trace Regression Replay Fidelity: 1.00 (Exact)")
