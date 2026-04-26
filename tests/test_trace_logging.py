import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schemas import AgentRequest, RouterDecision, ToolResult, AgentResponse, IntentEnum, StatusEnum

class TestTraceLogging(unittest.TestCase):
    def test_trace_id_propagation(self):
        # Ensure trace ID strictly propagates across all contracts seamlessly
        master_trace = "trace-uuid-abcdef-1024"
        
        req = AgentRequest(trace_id=master_trace, query="test sequence")
        dec = RouterDecision(trace_id=req.trace_id, intent=IntentEnum.SEARCH, reasoning="test", confidence=1.0)
        tool = ToolResult(trace_id=dec.trace_id, tool_name="test_tool", status=StatusEnum.OK, execution_time_ms=10)
        resp = AgentResponse(trace_id=tool.trace_id, status=StatusEnum.OK, result="ok", confidence=1.0, next_action="respond")

        self.assertEqual(req.trace_id, master_trace)
        self.assertEqual(dec.trace_id, master_trace)
        self.assertEqual(tool.trace_id, master_trace)
        self.assertEqual(resp.trace_id, master_trace)

if __name__ == '__main__':
    unittest.main()
