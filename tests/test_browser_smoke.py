import unittest
import asyncio
import sys, os
sys.path.insert(0, os.path.abspath('.'))

from capability_policy import PolicyState, CapabilityLevel
from action_schemas import ActionContract, OSActionType, ActionMode
from playwright_runtime import PlaywrightRuntime

class TestBrowserSmoke(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Allowlist strictly mapped isolating physical Chromium domains
        self.policy = PolicyState(
            level=CapabilityLevel.STANDARD,
            allowed_domains=["example.com", "example.org"],
            active_action_mode="interact"
        )
        self.runtime = PlaywrightRuntime(self.policy)
        await self.runtime.start()

    async def asyncTearDown(self):
        await self.runtime.stop()

    async def test_01_basic_navigation_and_read(self):
        """ Tests explicit Open -> Read sequences within allowed bounds mapping DOM precisely. """
        contract_open = ActionContract(
            trace_id="smoke-test-01",
            action_type=OSActionType.OPEN_URL,
            payload="https://example.com",
            required_mode=ActionMode.NAVIGATE,
            source_intent="smoke-testing-DOM"
        )
        
        res = await self.runtime.execute_action(contract_open)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("Example Domain", res["result"])

        contract_read = ActionContract(
            trace_id="smoke-test-02",
            action_type=OSActionType.READ_PAGE,
            required_mode=ActionMode.READ_ONLY,
            source_intent="read-target-text"
        )
        res_read = await self.runtime.execute_action(contract_read)
        self.assertEqual(res_read["status"], "SUCCESS")
        self.assertTrue(len(res_read["result"]) > 50)
        
    async def test_02_blocked_domain_rejection(self):
        """ Guarantees physical domain bounds cannot be bypassed. """
        contract_malicious = ActionContract(
            trace_id="smoke-test-03",
            action_type=OSActionType.OPEN_URL,
            payload="https://news.ycombinator.com", # NOT in allowlist specifically 
            required_mode=ActionMode.NAVIGATE,
            source_intent="bypass-test"
        )
        res = await self.runtime.execute_action(contract_malicious)
        self.assertEqual(res["status"], "BLOCKED")
        
    async def test_03_kill_switch_activation(self):
        """ Proves the Hard 15-action stop limit recursively drops infinite execution loops properly. """
        # Force max bounds manually cleanly offline
        self.runtime.action_counter = 15
        
        contract = ActionContract(
            trace_id="smoke-test-04",
            action_type=OSActionType.READ_PAGE,
            required_mode=ActionMode.READ_ONLY,
            source_intent="spam-test"
        )
        res = await self.runtime.execute_action(contract)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertIn("Kill-Switch", res["reason"])

if __name__ == "__main__":
    unittest.main()
