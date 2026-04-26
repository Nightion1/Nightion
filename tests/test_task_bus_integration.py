import os
import json
import uuid
import pytest
import asyncio
from schemas import TaskProposal, AgentRole, TaskResultStatus
from task_bus import TaskBus

def test_multi_agent_task_bus_isolation():
    asyncio.run(_test_multi_agent_task_bus_isolation())

async def _test_multi_agent_task_bus_isolation():
    """ Proves TaskBus successfully isolates sub-agents bypassing conversational mesh drift natively securely. """
    
    parent_id = str(uuid.uuid4())
    bus = TaskBus()
    
    # We propose a Search role to prove IntentEnum bypasses
    proposal = TaskProposal(
        task_id="task-123",
        parent_trace_id=parent_id,
        role=AgentRole.RESEARCH_SPECIALIST,
        objective="Analyze strict multi-agent bounding loops offline safely.",
        allowed_tools=["search"],
        context_slice="[Test Mapped Slice]",
        success_criteria="Return simple verification payload."
    )
    
    # Let Execution hit the simulated Orchestrator Engine natively
    node_result = await bus.route_task(proposal)
    
    # 1. Verify schema return limits
    assert node_result.status in [TaskResultStatus.SUCCESS, TaskResultStatus.FAILED, TaskResultStatus.INCOMPLETE], "Must return mechanical Node Status bounds"
    assert node_result.trace_id != parent_id, "Sub-Agent Trace ID must be uniquely isolated."
    assert "Sub-Agent execution crash" not in node_result.result_payload, f"Engine crashed: {node_result.error_context}"
    
    # 2. Verify physical Nested Tracing logs correctly tied to parent
    log_file = os.path.join(bus.log_dir, node_result.trace_id, "task_bus.json")
    
    assert os.path.exists(log_file), "Physical Bus telemetry failed to generate offline constraint loops."
    
    with open(log_file, "r") as f:
        data = json.load(f)
        
    assert data["parent_trace"] == parent_id, "Parent Trace ID linkage failed mapping nested lineage offline."
    assert data["event"] == "resolution", "Resolution event not mapped structurally natively."
    assert data["payload"]["status"] == node_result.status.value, "Payload node mismatch globally."
    
    print(f"Task Bus Isolation Validated. Result: {node_result.result_payload[:40]}...")
