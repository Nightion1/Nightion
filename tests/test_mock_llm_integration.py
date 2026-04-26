import unittest
from schemas import AgentRequest, IntentEnum, StatusEnum, ThoughtSchema
from orchestrator import Orchestrator
from tool_router import ToolRouter
from schemas import RouterDecision

class MockRouter(ToolRouter):
    async def route(self, request: AgentRequest) -> RouterDecision:
        return RouterDecision(trace_id=request.trace_id, intent=IntentEnum.CODE, confidence=0.9, reasoning="Mock deterministic routing to CODE")

class TestMockLLMIntegration(unittest.IsolatedAsyncioTestCase):

    async def test_semantic_feedback_loop_native(self):
        """ Prove that the Orchestrator loops context back to the Mock LLM natively via real Sandbox failures. """
        
        router = MockRouter()
        orchestrator = Orchestrator(router=router, max_retries=3)
        self.mock_call_count = 0
        
        async def mock_analyze(query, intent, policy_state, feedback, memory_payload=None):
            self.mock_call_count += 1
            if self.mock_call_count == 1:
                return ThoughtSchema(
                    understanding="Executing flawed execution.",
                    plan="Execute bad target.",
                    steps=["bad_target_step_undefined"], # Will trigger python NameError inside physical sandbox
                    uncertainty=0.1,
                    requires_tools=True,
                    context_strategy="Flawed Code"
                )
            else:
                self.assertIsNotNone(feedback, "Feedback was None on attempt 2") 
                self.assertTrue("NameError" in feedback or "bad_target_step_undefined" in feedback, "Sandbox Traceback missed from Feedback String Array")
                return ThoughtSchema(
                    understanding="Fixing execution natively.",
                    plan="Execute correct target.",
                    steps=["print('success_recovery')"], 
                    uncertainty=0.0,
                    requires_tools=True,
                    context_strategy="Corrected Code"
                )
                
        orchestrator.reasoning.analyze = mock_analyze
        
        # Execute the loop natively (Real Sandbox, Real Verifier, Real Mission Planner)
        request = AgentRequest(query="Run the integration simulation natively offline", trace_id="mock_trace_native")
        response = await orchestrator.execute_task(request)
        
        self.assertEqual(self.mock_call_count, 2, "Orchestrator did not dynamically loop Replanning accurately.")
        self.assertEqual(response.status, StatusEnum.OK, "Recovery failed entirely bypassing limit bounds.")
        self.assertIn("success_recovery", str(response.result), "Second execution target missed stdout completion.")

if __name__ == '__main__':
    unittest.main()
