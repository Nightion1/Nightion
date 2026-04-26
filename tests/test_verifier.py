import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verifier import Verifier
from schemas import ToolResult, StatusEnum, VerificationDecision

class TestVerifier(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.verifier = Verifier()

    async def test_blocked_tool_result(self):
        tool_res = ToolResult(
            trace_id="1", tool_name="sandbox", status=StatusEnum.BLOCKED, 
            output=None, error="Blocked by sandbox", execution_time_ms=10
        )
        res = await self.verifier.verify("query", tool_res, "1")
        self.assertEqual(res.decision, VerificationDecision.FAIL)
        self.assertEqual(res.severity, "high")
        self.assertIsNotNone(res.suggested_fix)

    async def test_empty_output(self):
        tool_res = ToolResult(
            trace_id="2", tool_name="sandbox", status=StatusEnum.OK, 
            output="", error=None, execution_time_ms=10
        )
        res = await self.verifier.verify("query", tool_res, "2")
        self.assertEqual(res.decision, VerificationDecision.FAIL)
        self.assertEqual(res.severity, "medium")

    async def test_successful_validation(self):
        tool_res = ToolResult(
            trace_id="3", tool_name="sandbox", status=StatusEnum.OK, 
            output="Expected data", error=None, execution_time_ms=10
        )
        res = await self.verifier.verify("query", tool_res, "3")
        self.assertEqual(res.decision, VerificationDecision.PASS)
        self.assertEqual(res.status, StatusEnum.OK)

if __name__ == '__main__':
    unittest.main()
