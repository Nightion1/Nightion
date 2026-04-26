import pytest
import asyncio
from schemas import MissionProfile, MissionClass, StatusEnum
from mission_executor import MissionExecutor
from orchestrator import Orchestrator
from tool_router import ToolRouter
import policy_packs

def test_mission_evaluations_and_gates():
    """ Evaluates explicitly blocked UI paths proving exact UI trace rejection semantics cleanly natively offline securely. """
    asyncio.run(_test_mission_evaluations_and_gates())

async def _test_mission_evaluations_and_gates():
    router = ToolRouter()
    orch = Orchestrator(router=router, max_retries=1)
    executor = MissionExecutor(orchestrator=orch)
    
    # 1. Fall-back Benchmark: Reject LOCAL_ADMIN using implicit Mock overriding gracefully offline
    old_method = policy_packs.HumanApprovalGate.request_approval
    policy_packs.HumanApprovalGate.request_approval = lambda msg, c, obj: False # Simulate operator click: REJECT
    
    admin_mission = MissionProfile(
        mission_id="bench-01",
        mission_class=MissionClass.LOCAL_ADMIN,
        objective="Delete system log dumps completely.",
        success_criteria="Space verified freed locally offline."
    )
    
    res = await executor.execute_mission(admin_mission)
    
    # Assert specific Failure bindings isolating bounds natively tracking score limits linearly off
    assert res.score.completion_status == StatusEnum.BLOCKED, "Mission Gate missed the explicit Operator native UI refusal schema stably offline."
    assert "Human Approval Gateway Rejection" in res.final_output, "Semantic Rejection Trace was missing causing UI generic failures linearly natively."
    assert res.score.gate_reason == "Operator declined Local Admin limits cleanly offline."
    assert res.score.accuracy_score == 0.0, "Score corrupted computing BLOCKED drops stably."
    assert res.score.latency_ms > 0
    
    # Reset Mock securely
    policy_packs.HumanApprovalGate.request_approval = old_method
    
    print("Mission Evaluation Suite Benchmark 01 -> PASSED (Human Gate Rejection Integrity)")
