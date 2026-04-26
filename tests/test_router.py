import unittest
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tool_router import ToolRouter
from schemas import AgentRequest, IntentEnum

class TestRouter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.router = ToolRouter()

    async def test_classification_greeting(self):
        req = AgentRequest(trace_id="1-g", query="hi")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.GREETING)

    async def test_classification_app_control(self):
        req = AgentRequest(trace_id="1", query="open notepad and click the file menu")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.APP_CONTROL)

    async def test_classification_browser_automation(self):
        req = AgentRequest(trace_id="1-b", query="open example.com and scroll down")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.BROWSER_AUTOMATION)

    async def test_classification_search(self):
        req = AgentRequest(trace_id="2", query="web search for the latest CUDA version")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.SEARCH)

    async def test_classification_code(self):
        req = AgentRequest(trace_id="3", query="write a python script for merge sort")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.CODE)

    async def test_classification_dsa(self):
        req = AgentRequest(trace_id="4", query="explain BFS with complexity")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.DSA)

    async def test_classification_general_fallback(self):
        req = AgentRequest(trace_id="5", query="help me with this idea")
        decision = await self.router.route(req)
        self.assertEqual(decision.intent, IntentEnum.GENERAL)

    def test_greeting_returns_conversational_response(self):
        from llm_adapter import LocalizedLLMAdapter
        adapter = LocalizedLLMAdapter()
        # Mocking policy_state since it's required by the signature
        thought = adapter._fallback_mock("hi", intent="general", policy_state={})
        
        self.assertEqual(thought.plan, "Hello! How can I help you today?")
        self.assertNotIn("Direct conversational mapping", thought.plan)
        self.assertNotIn("planner", thought.plan.lower())

if __name__ == '__main__':
    unittest.main()
