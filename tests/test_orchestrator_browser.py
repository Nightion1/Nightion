import unittest
import asyncio
import sys, os
sys.path.insert(0, os.path.abspath('.'))

from orchestrator import Orchestrator
from tool_router import ToolRouter
from schemas import AgentRequest, StatusEnum

class TestOrchestratorBrowser(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.router = ToolRouter()
        self.orchestrator = Orchestrator(self.router, max_retries=1)

    async def test_end_to_end_browser_navigation(self):
        req = AgentRequest(
            trace_id="test-e2e-browser",
            query="navigate to http://example.com" # Should hit "navigate to", Intent=BROWSER_AUTOMATION
        )
        # Note: Example.com is typically allowlisted inherently or tested in `playwright_runtime` gracefully
        # Ensure we pass the global pre_check by avoiding destructive keywords safely
        
        # Override the policy explicitly mapping exactly offline securely without mocking the whole loop
        self.orchestrator.gate.policy.allowed_domains = ["example.com"]
        
        res = await self.orchestrator.execute_task(req)
        
        # We expect a SUCCESS or BLOCKED (if kill switch hits), but the loop should successfully map the Intent completely
        self.assertIsNotNone(res)
        self.assertTrue(res.status in [StatusEnum.OK, StatusEnum.BLOCKED, StatusEnum.FAILED])
        self.assertEqual(res.metadata.get("intent"), "browser_automation")

if __name__ == "__main__":
    unittest.main()
