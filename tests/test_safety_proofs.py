import unittest
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.desktop import DesktopTool
from schemas import StatusEnum

class TestSafetyProofs(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tool = DesktopTool()

    async def test_llm_confusion_resistance(self):
        # PROOF POINT: 
        # Even if the LLM/Router incorrectly classifies a destructive request as a safe generic action, 
        # the payload execution boundary MUST override and definitively refuse it.
        # Simulating LLM mistakenly routing 'format C:' as a benign 'open' action.
        res = await self.tool.execute(
            action="open", 
            target="C:\\", 
            payload={"cmd": "format"}, 
            trace_id="safe_proof_1"
        )
        self.assertEqual(res.status, StatusEnum.BLOCKED, "Safety gate failed to catch structural keyword inside payload mapping.")

if __name__ == '__main__':
    unittest.main()
