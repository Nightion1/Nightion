import unittest
import asyncio
from schemas import AgentRequest, IntentEnum, StatusEnum, ThoughtSchema, RouterDecision
from orchestrator import Orchestrator
from tool_router import ToolRouter
from llm_adapter import LocalizedLLMAdapter

class MockRouter(ToolRouter):
    async def route(self, request: AgentRequest) -> RouterDecision:
        return RouterDecision(trace_id=request.trace_id, intent=IntentEnum.CODE, confidence=1.0, reasoning="Testing robustness")

class TestCodeExecutionRobustness(unittest.IsolatedAsyncioTestCase):

    async def test_reject_natural_language_step(self):
        """ Verify that the orchestrator rejects natural language steps for the CODE intent instead of running them. """
        router = MockRouter()
        orchestrator = Orchestrator(router=router, max_retries=2)
        
        async def mock_analyze(query, intent, policy_state, feedback, memory_payload=None):
            return ThoughtSchema(
                understanding="Test rejection.",
                plan="Plan with NL step.",
                steps=["This is natural language, not code."],
                uncertainty=0.1,
                requires_tools=True,
                context_strategy="Test"
            )
        
        orchestrator.reasoning.analyze = mock_analyze
        
        request = AgentRequest(query="test nl rejection", trace_id="test_nl_rejection")
        response = await orchestrator.execute_task(request)
        
        # Should fail because the retry loop will eventually exhaust or it returns a failed response
        # In our implementation, we 'break' the while loop and it goes to the next retry attempt.
        # Since we use max_retries=2, and both attempts will have NL steps, it should return FAILED.
        self.assertEqual(response.status, StatusEnum.FAILED)
        self.assertIn("VALIDATION FAILED", response.error)

    def test_llm_adapter_fallback_mock_code_feedback(self):
        """ Verify that llm_adapter fallback mock returns valid code for CODE intent with feedback. """
        adapter = LocalizedLLMAdapter()
        thought = adapter._fallback_mock(
            query="write binary search", 
            intent="code", 
            policy_state={}, 
            feedback="SyntaxError: invalid syntax"
        )
        
        self.assertEqual(thought.requires_tools, True)
        self.assertTrue(len(thought.steps) > 0)
        
        # Verify the step is valid Python
        import ast
        for step in thought.steps:
            try:
                ast.parse(step)
            except SyntaxError:
                self.fail(f"Fallback mock returned invalid Python step: {step}")

if __name__ == '__main__':
    unittest.main()
