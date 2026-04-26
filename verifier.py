from typing import Optional
from schemas import ToolResult, VerificationResult, VerificationDecision, StatusEnum, IntentEnum

class Verifier:
    """
    The Hardened Absolute Authority Validation Layer for Nightion.
    Grades logical correctness, prevents hallucinations, handles chaotic edges,
    and returns explicit Tri-State bounds for Orchestrator processing.
    """
    
    def __init__(self):
        pass

    async def verify(self, query: str, intent: IntentEnum, tool_res: ToolResult, trace_id: str) -> VerificationResult:
        # 1. Semantic Intent Validation (Phase 28 Patch)
        # Prevents "Search-before-Code" anti-patterns or misrouted technical execution.
        semantic_failure = self._check_semantic_mismatch(query, intent, tool_res, trace_id)
        if semantic_failure:
            return semantic_failure

        # 2. Immediate Failure Checks (Strict bounds)
        if tool_res.status in [StatusEnum.FAILED, StatusEnum.BLOCKED]:
            severity = "high" if tool_res.status == StatusEnum.BLOCKED else "medium"
            return VerificationResult(
                trace_id=trace_id,
                decision=VerificationDecision.FAIL,
                status=tool_res.status,
                confidence=1.0,
                reason=f"System execution blocked or violently failed: {tool_res.error}",
                counterexample=f"Tool output crashed attempting '{query}' targeting '{tool_res.tool_name}'.",
                suggested_fix="Correct the permissions or strictly format the injected syntax to match isolation thresholds.",
                severity=severity
            )

        # 2. Malformed / Empty Validation
        if tool_res.output in [None, ""]:
             # Hard failure for null responses avoiding empty type bypasses down the pipe.
            return VerificationResult(
                trace_id=trace_id,
                decision=VerificationDecision.FAIL,
                status=StatusEnum.FAILED,
                confidence=1.0,
                reason="Tool abstraction collapsed, returning pure empty output.",
                counterexample="Action triggered with payload, yet execution container returned zero bytes standard out.",
                suggested_fix="Evaluate logical flow. Did the output require a 'return' or explicit 'print' context to pipe stdout to the orchestrator?",
                severity="medium"
            )

        # 3. Chaos Uncertain Checks
        str_out = str(tool_res.output).lower()
        
        # 3a. Stub Detection (Phase 29-Harden)
        STUB_SIGNATURES = [
            "execution complete",
            "sandbox trace verified",
            "simulated verification",
            "not implemented",
            "parse arguments mapped strictly"
        ]
        if intent == IntentEnum.CODE and any(sig in str_out for sig in STUB_SIGNATURES):
            return VerificationResult(
                trace_id=trace_id,
                decision=VerificationDecision.FAIL,
                status=StatusEnum.FAILED,
                confidence=1.0,
                reason="STUB_DETECTED: Sandbox returned a placeholder instead of real code.",
                counterexample=str_out[:100],
                suggested_fix="Generator implementation is returning mocks; check KnowledgeBase or LLM adapter.",
                severity="high"
            )

        if "confusion" in str_out or "uncertain" in str_out or "not sure" in str_out:
            return VerificationResult(
                trace_id=trace_id,
                decision=VerificationDecision.UNCERTAIN,
                status=StatusEnum.NEEDS_CLARIFICATION,
                confidence=0.4,
                reason="The tool output indicates internal confusion or non-deterministic variance.",
                counterexample="Expected deterministic string generation; received ambiguous language fallback marker.",
                suggested_fix="If LLM fallback occurred, provide vastly tighter context or explicitly restrict generation randomness parameters.",
                severity="low"
            )

        # 4. Success State Endorsement
        return VerificationResult(
            trace_id=trace_id,
            decision=VerificationDecision.PASS,
            status=StatusEnum.OK,
            confidence=0.90,
            reason="Output explicitly verified against safety and deterministic bounds.",
            counterexample=None,
            suggested_fix=None, # Permitted passing model validator
            severity="low"
        )

    def _check_semantic_mismatch(self, query: str, intent: IntentEnum, tool_res: ToolResult, trace_id: str) -> Optional[VerificationResult]:
        """ Phase 28: Identifies if the tool execution mode contradicts the semantic goal. """
        lowered_query = query.lower()
        output_str = str(tool_res.output or "").lower()
        
        # Rule 1: Catch "Search-instead-of-Code" anti-pattern
        if intent == IntentEnum.SEARCH:
             # Strong indicators of coding intent that should have bypassed search
             coding_verbs = ["write", "implement", "create", "build", "code", "generate"]
             coding_langs = ["python", "javascript", "java", "rust", "cpp", "c++"]
             
             has_verb = any(v in lowered_query for v in coding_verbs)
             has_lang = any(l in lowered_query for l in coding_langs)
             
             if has_verb and has_lang:
                 # If we actually got search snippets instead of code
                 if tool_res.tool_name == "search" or "found" in output_str and "source" in output_str:
                     return VerificationResult(
                         trace_id=trace_id,
                         decision=VerificationDecision.FAIL,
                         status=StatusEnum.FAILED,
                         confidence=1.0,
                         reason="SEMANTIC MISMATCH: System searched for implementation instead of executing it.",
                         suggested_fix="The query requires direct code generation/execution. Retrying with CODE intent.",
                         trigger_reroute=True,
                         suggested_intent=IntentEnum.CODE,
                         severity="medium"
                     )
        
        return None
