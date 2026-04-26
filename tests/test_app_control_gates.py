import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guards import evaluate_action, ActionRisk
from schemas import ToolResult, StatusEnum
from tools.desktop import DesktopTool
import asyncio

class TestAppControlGates(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tool = DesktopTool()

    async def test_confirmation_gate_flag(self):
        # Deletion actions must be blocked and explicitly flagged as CRITICAL requesting confirmation.
        res = await self.tool.execute("delete", "system32", {}, "gate1")
        self.assertEqual(res.status, StatusEnum.BLOCKED)
        self.assertTrue(res.requires_confirmation)
        
    async def test_safe_gate_passthrough(self):
        res = await self.tool.execute("scroll", "down", {}, "gate2")
        self.assertEqual(res.status, StatusEnum.OK)
        self.assertFalse(res.requires_confirmation)

    async def test_destructive_keywords_in_target(self):
        # Action is "open", but target contains "delete" -> could bypass naive action-only checks
        res = await self.tool.execute("open", "delete_everything.exe", {}, "gate3")
        # In MVP guards, evaluated string is f"{action} {target} {payload}". So "delete" will be caught!
        self.assertEqual(res.status, StatusEnum.BLOCKED)
        self.assertTrue(res.requires_confirmation)

if __name__ == '__main__':
    unittest.main()
