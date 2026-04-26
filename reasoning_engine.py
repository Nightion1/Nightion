from schemas import ThoughtSchema
from typing import Optional, Dict, Any
from llm_adapter import LocalizedLLMAdapter

class ReasoningEngine:
    """
    The Cognitive Strategy layer driving semantic planning strictly via the localized LLM.
    Determines HOW to think and dictates a structurally guaranteed ThoughtSchema 
    for the Orchestrator to mathematically rely on.
    """
    
    def __init__(self):
        self.llm = LocalizedLLMAdapter()

    async def analyze(self, query: str, intent: str, policy_state: Dict[str, Any], feedback: Optional[str] = None, memory_payload: Optional[Dict[str, Any]] = None) -> ThoughtSchema:
        """ Constructs a conscious mental map of the problem pushing strict constraints to the LLM backend natively. """
        
        # Dispatch to the LLM structural processor maintaining strict schema guarantees
        thought = await self.llm.generate_structured_thought(
            query=query,
            intent=intent,
            policy_state=policy_state,
            feedback=feedback,
            memory=memory_payload
        )
        
        return thought
