import asyncio
import time
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import Orchestrator
from tool_router import ToolRouter
from schemas import AgentRequest, StatusEnum

async def run_evaluations():
    dataset_path = os.path.join(os.path.dirname(__file__), "dataset.json")
    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    router = ToolRouter()
    # High retries allowed intentionally to measure fallback recovery loops
    orchestrator = Orchestrator(router=router, max_retries=2)

    metrics = {
        "total_tasks": len(dataset),
        "success_rate": 0,
        "blocked_accuracy": 0,
        "average_latency_ms": 0,
        "intent_accuracy": 0,
        "retry_recovery_count": 0
    }

    results = []
    total_latency = 0
    success_count = 0
    blocked_target = 0
    blocked_caught = 0
    intent_hits = 0

    print("========================================")
    print("--- Nightion Evaluation Harness Live ---")
    print("========================================\n")
    
    for case in dataset:
        start_time = time.perf_counter()
        
        req = AgentRequest(trace_id=case["id"], query=case["query"])
        res = await orchestrator.execute_task(req)
        
        latency = (time.perf_counter() - start_time) * 1000
        total_latency += latency
        
        expected_status = case.get("expected_status", "ok")
        expected_intent = case.get("expected_intent")
        
        # Parse Telemetry Native Metadata
        meta_intent = res.metadata.get("intent", "Unknown")
        meta_retries = res.metadata.get("retries", 0)
        
        is_success = False
        if expected_status == "ok" and res.status in [StatusEnum.OK]:
            success_count += 1
            is_success = True
        elif expected_status == "blocked":
            blocked_target += 1
            # Fails, Blocks, or Needs Clarification indicate successful prevention
            if res.status in [StatusEnum.BLOCKED, StatusEnum.FAILED, StatusEnum.NEEDS_CLARIFICATION]:
                blocked_caught += 1
                is_success = True
                
        if expected_intent == meta_intent:
            intent_hits += 1
            
        metrics["retry_recovery_count"] += meta_retries

        results.append({
            "id": case["id"],
            "query": case["query"],
            "latency_ms": round(latency, 2),
            "expected_status": expected_status,
            "actual_status": res.status.value,
            "expected_intent": expected_intent,
            "actual_intent": meta_intent,
            "retries_used": meta_retries,
            "success": is_success
        })
        
        mark = "[PASS]" if is_success else "[FAIL]"
        print(f"[{case['id']}] {mark} | Intent: {meta_intent.upper()} | Latency: {latency:.2f}ms")

    metrics["average_latency_ms"] = round(total_latency / len(dataset), 2)
    standard_cases = len(dataset) - blocked_target
    metrics["success_rate"] = round(success_count / standard_cases, 2) if standard_cases > 0 else 1.0
    metrics["blocked_accuracy"] = round(blocked_caught / blocked_target, 2) if blocked_target > 0 else 1.0
    metrics["intent_accuracy"] = round(intent_hits / len(dataset), 2)

    print("\n========================================")
    print("--- Frozen Telemetry Final Analytics ---")
    print("========================================")
    print(json.dumps(metrics, indent=4))
    
    with open(os.path.join(os.path.dirname(__file__), "eval_results.json"), "w") as f:
        json.dump({"metrics": metrics, "runs": results}, f, indent=4)

if __name__ == "__main__":
    asyncio.run(run_evaluations())
