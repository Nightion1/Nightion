import unittest
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool_router import ToolRouter
from schemas import AgentRequest, IntentEnum

class TestRouterAdversarial(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.router = ToolRouter()

    async def test_conflict_resolution(self):
        # "open app" (APP_CONTROL: 1 match 'open') + "search the web" (SEARCH: 2 matches 'search', 'web') + "write code" (CODE: 2 matches)
        # Search has higher priority than Code, and both outscore App_Control's single match length scaling.
        req = AgentRequest(trace_id="adv1", query="write code to search the web and open an app")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.SEARCH)

    async def test_vague_intents(self):
        # Very vague inputs should safely fallback to GENERAL rather than guessing Code/Search.
        req = AgentRequest(trace_id="adv2", query="do it please")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.GENERAL)

    async def test_extreme_payload_length(self):
        # Checking if regex parsing chokes on huge inputs (simulating DDoS/buffer pressure)
        huge_str = "code " * 10000
        req = AgentRequest(trace_id="adv3", query=huge_str)
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.CODE)

if __name__ == '__main__':
    unittest.main()
