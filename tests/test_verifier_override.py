import unittest
import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verifier import Verifier
from schemas import ToolResult, StatusEnum, VerificationDecision

class TestVerifierOverride(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.verifier = Verifier()

    async def test_override_feedback_injection(self):
        # A tool failing contextually MUST prompt the Verifier to enforce `suggested_fix` injections.
        tool_res = ToolResult(
            trace_id="ovr-1", tool_name="sandbox_python", status=StatusEnum.FAILED, 
            output=None, error="SyntaxError: invalid syntax", execution_time_ms=500
        )
        ver_res = await self.verifier.verify("write code", tool_res, "ovr-1")
        
        self.assertEqual(ver_res.decision, VerificationDecision.FAIL)
        self.assertEqual(ver_res.severity, "medium")
        self.assertTrue(len(ver_res.suggested_fix or "") > 0)
        
if __name__ == '__main__':
    unittest.main()
