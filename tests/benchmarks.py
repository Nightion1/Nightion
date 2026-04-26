import asyncio
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import Orchestrator
from tool_router import ToolRouter
from schemas import AgentRequest

async def run_benchmarks():
    router = ToolRouter()
    # High retries allowed because we want to measure standard success rates natively.
    orchestrator = Orchestrator(router=router, max_retries=1)

    scenarios = [
        {"name": "DSA Algorithms", "query": "write an optimized sliding window algorithm"},
        {"name": "Code Debugging", "query": "fix this null pointer exception"},
        {"name": "Web Searching", "query": "latest version of python"},
        {"name": "Native Control", "query": "open chrome browser"},
        {"name": "Mixed Workflow", "query": "search the web for python then write a function"}
    ]

    print("================================")
    print("--- Nightion Benchmark Suite ---")
    print("================================\n")
    
    for s in scenarios:
        start = time.perf_counter()
        req = AgentRequest(trace_id=f"bench_{s['name'].replace(' ', '_')}", query=s["query"])
        res = await orchestrator.execute_task(req)
        latency = (time.perf_counter() - start) * 1000
        print(f"[{s['name']}]")
        print(f" -> Result Status:  {res.status.value.upper()}")
        print(f" -> Latency:        {latency:.2f}ms")
        print(f" -> Confidence:     {res.confidence:.2f}")
        print("-" * 32)

if __name__ == "__main__":
    asyncio.run(run_benchmarks())
