import unittest
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import Orchestrator
from tool_router import ToolRouter
from schemas import AgentRequest, StatusEnum, IntentEnum

class TestNightionFixes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        router = ToolRouter()
        self.orchestrator = Orchestrator(router=router, max_retries=3)

    async def test_math_query(self):
        # "what is 2+2" should now be handled via GENERAL -> LLM (Mock in this case) -> CODE
        req = AgentRequest(trace_id="math-1", query="what is 2+2")
        res = await self.orchestrator.execute_task(req)
        # In mock mode, 2+2 triggers the CODE mock which prints the result.
        # The key is that it doesn't loop forever!
        self.assertEqual(res.status, StatusEnum.OK)
        self.assertIn("4", res.result)

    async def test_identity_query(self):
        req = AgentRequest(trace_id="ident-1", query="who created you")
        res = await self.orchestrator.execute_task(req)
        self.assertEqual(res.status, StatusEnum.OK)
        self.assertIn("Nightion development team", res.result)

    async def test_table_query(self):
        req = AgentRequest(trace_id="table-1", query="write table of 4")
        res = await self.orchestrator.execute_task(req)
        self.assertEqual(res.status, StatusEnum.OK)
        self.assertIn("4 x 1 = 4", res.result)

    async def test_loop_exhaustion_prevention(self):
        # Simulate a case where reasoning returns 0 steps but requires_tools=True
        # With the fix in MissionController, this should complete instantly (effectively a no-op success)
        # or at least not loop.
        from unittest.mock import patch, MagicMock
        from schemas import ThoughtSchema

        mock_thought = ThoughtSchema(
            understanding="Empty loop test",
            plan="Do nothing but require tools",
            steps=[],
            uncertainty=0.1,
            requires_tools=True,
            context_strategy="Test"
        )
        
        with patch('reasoning_engine.ReasoningEngine.analyze', return_value=mock_thought):
            req = AgentRequest(trace_id="loop-1", query="empty loop test")
            res = await self.orchestrator.execute_task(req)
            self.assertEqual(res.status, StatusEnum.OK)
            self.assertIn("Sequence Executed", res.result)

if __name__ == '__main__':
    unittest.main()
