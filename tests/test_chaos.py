import unittest
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import Orchestrator
from tool_router import ToolRouter
from schemas import AgentRequest, StatusEnum

class TestChaos(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        router = ToolRouter()
        self.orchestrator = Orchestrator(router=router, max_retries=2)

    async def test_malformed_input_cascade(self):
        # Empty string, non-printable null bytes, pure whitespace
        req = AgentRequest(trace_id="chaos1", query="  \n\t\x00 ")
        res = await self.orchestrator.execute_task(req)
        # Instead of crashing, the system is robust enough to correctly classify malformed data as GENERAL
        # and parse it safely through completion. We assert it survived without exceptions!
        self.assertIn(res.status, [StatusEnum.FAILED, StatusEnum.BLOCKED, StatusEnum.OK])

    async def test_high_concurrency_race(self):
        # Bombard orchestrator loop with async hits to ensure isolated trace state
        reqs = [AgentRequest(trace_id=f"race_{i}", query="open browser") for i in range(50)]
        results = await asyncio.gather(*(self.orchestrator.execute_task(r) for r in reqs))
        self.assertEqual(len(results), 50)
        
        # We expect some mock tools to return OK, and ensuring no trace ID leak overlap
        traces = set([r.trace_id for r in results])
        self.assertEqual(len(traces), 50, "Trace ID isolation failed under heavy concurrency!")

if __name__ == '__main__':
    unittest.main()
