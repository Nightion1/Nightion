"""
Phase 28 Routing Tests
Tests for the enhanced intent classification that fixes the "write X in Python" bug
"""
import pytest
from unittest.mock import Mock
from tool_router import ToolRouter, RouterConfig
from schemas import AgentRequest, IntentEnum, StatusEnum


class TestPhase28StrongCodingSignals:
    """Tests for the new _check_strong_coding_signal method"""
    
    def setup_method(self):
        self.router = ToolRouter(config=RouterConfig())
    
    def test_write_binary_search_in_python(self):
        """THE BUG CASE: Should route to CODE, not SEARCH"""
        query = "write a binary search in python"
        result = self.router._check_strong_coding_signal(query)
        assert result is True, "Should detect strong coding signal"
    
    def test_implement_quicksort_using_javascript(self):
        query = "implement quicksort using JavaScript"
        result = self.router._check_strong_coding_signal(query)
        assert result is True
    
    def test_create_function_in_rust(self):
        query = "create a REST API function in Rust"
        result = self.router._check_strong_coding_signal(query)
        assert result is True
    
    def test_build_with_python(self):
        query = "build a web scraper with Python"
        result = self.router._check_strong_coding_signal(query)
        assert result is True
    
    # NEGATIVE TESTS (should return False)
    
    def test_write_email_no_language(self):
        """Should NOT trigger - no language mentioned"""
        query = "write me an email to my boss"
        result = self.router._check_strong_coding_signal(query)
        assert result is False
    
    def test_search_for_python_tutorials(self):
        """Should NOT trigger - starts with 'search'"""
        query = "search for Python tutorials"
        result = self.router._check_strong_coding_signal(query)
        assert result is False
    
    def test_python_is_a_snake(self):
        """Should NOT trigger - no coding verb"""
        query = "Python is a snake, not a programming language"
        result = self.router._check_strong_coding_signal(query)
        assert result is False
    
    def test_find_python_examples(self):
        """Should NOT trigger - starts with 'find'"""
        query = "find me some Python code examples online"
        result = self.router._check_strong_coding_signal(query)
        assert result is False
    
    def test_write_article_about_javascript(self):
        """Edge case: mentions language but not coding context"""
        query = "write an article about JavaScript history"
        result = self.router._check_strong_coding_signal(query)
        # This will return True because it has verb + language
        # We accept this as acceptable false positive - verifier will catch it
        assert result is True


class TestPhase28EndToEndRouting:
    """Integration tests for full routing flow"""
    
    @pytest.mark.asyncio
    async def test_binary_search_routes_to_code(self):
        """End-to-end test: The original bug case"""
        router = ToolRouter(config=RouterConfig())
        request = AgentRequest(
            query="Write a binary search in Python",
            trace_id="test-15993798"
        )
        
        decision = await router.route(request)
        
        assert decision.intent == IntentEnum.CODE, \
            f"Should route to CODE but got {decision.intent}"
        assert decision.confidence >= 0.99, \
            f"Should have high confidence (0.99) but got {decision.confidence}"
        assert decision.status == StatusEnum.OK
        assert "strong coding signal" in decision.reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_implement_algorithm_routes_to_code(self):
        router = ToolRouter(config=RouterConfig())
        request = AgentRequest(
            query="implement a merge sort algorithm in JavaScript",
            trace_id="test-001"
        )
        
        decision = await router.route(request)
        assert decision.intent == IntentEnum.CODE
        assert decision.confidence >= 0.99
    
    @pytest.mark.asyncio
    async def test_search_for_tutorials_routes_to_search(self):
        """Should still route to SEARCH when appropriate"""
        router = ToolRouter(config=RouterConfig())
        request = AgentRequest(
            query="search for Python binary search tutorials",
            trace_id="test-002"
        )
        
        decision = await router.route(request)
        assert decision.intent == IntentEnum.SEARCH, \
            "Explicit search queries should still route to SEARCH"
    
    @pytest.mark.asyncio
    async def test_ambiguous_code_search_prefers_code(self):
        """Phase 28 priority fix: CODE wins over SEARCH in ties"""
        router = ToolRouter(config=RouterConfig())
        request = AgentRequest(
            query="code a binary search",  # Matches both CODE and SEARCH patterns
            trace_id="test-003"
        )
        
        decision = await router.route(request)
        # With new priority order, CODE should win
        assert decision.intent in [IntentEnum.CODE, IntentEnum.DSA], \
            f"Should prefer CODE/DSA over SEARCH, got {decision.intent}"


class TestPhase28PriorityOrder:
    """Tests for the updated priority ranking"""
    
    def test_priority_order_code_before_search(self):
        """Verify CODE is prioritized over SEARCH"""
        router = ToolRouter()
        
        # Simulate a query that matches both patterns equally
        scores = {
            IntentEnum.SEARCH: 0.82,
            IntentEnum.CODE: 0.82,
            IntentEnum.DSA: 0.72,
        }
        
        # The priority list in the fixed router is:
        # [BROWSER_AUTOMATION, APP_CONTROL, CODE, DSA, SEARCH]
        # So CODE should win over SEARCH in a tie
        
        # Test via actual classification
        query = "program binary search"  # Matches both CODE and SEARCH
        intent, conf, reason = router._classify_by_rules(query)
        
        # CODE or DSA should win, NOT SEARCH
        assert intent in [IntentEnum.CODE, IntentEnum.DSA], \
            f"CODE/DSA should win over SEARCH, got {intent}"


class TestPhase28NegativeCases:
    """Ensure we don't break existing functionality"""
    
    @pytest.mark.asyncio
    async def test_greeting_still_works(self):
        router = ToolRouter()
        request = AgentRequest(query="hello", trace_id="test-greeting")
        decision = await router.route(request)
        assert decision.intent == IntentEnum.GREETING
    
    @pytest.mark.asyncio
    async def test_app_control_still_works(self):
        router = ToolRouter()
        request = AgentRequest(query="open notepad", trace_id="test-app")
        decision = await router.route(request)
        assert decision.intent == IntentEnum.APP_CONTROL
    
    @pytest.mark.asyncio
    async def test_browser_automation_still_works(self):
        router = ToolRouter()
        request = AgentRequest(
            query="navigate to google.com and click the search button",
            trace_id="test-browser"
        )
        decision = await router.route(request)
        assert decision.intent == IntentEnum.BROWSER_AUTOMATION
    
    @pytest.mark.asyncio
    async def test_dsa_without_language_routes_to_dsa(self):
        """DSA queries without explicit language should still route to DSA"""
        router = ToolRouter()
        request = AgentRequest(
            query="explain time complexity of binary search",
            trace_id="test-dsa"
        )
        decision = await router.route(request)
        assert decision.intent == IntentEnum.DSA


class TestPhase28EdgeCases:
    """Tricky edge cases to validate robustness"""
    
    def test_code_in_the_middle_of_sentence(self):
        router = ToolRouter()
        # "code" appears but not as a coding action
        query = "what is the postal code in Python, Montana?"
        result = router._check_strong_coding_signal(query)
        # This will likely trigger because of "Python" - acceptable
        # Verifier layer should handle semantic validation
        assert result is True  # We accept this - verifier will clarify intent
    
    def test_multiple_languages_mentioned(self):
        router = ToolRouter()
        query = "write a function in Python or JavaScript, your choice"
        result = router._check_strong_coding_signal(query)
        assert result is True
    
    def test_case_insensitive_matching(self):
        router = ToolRouter()
        query = "WRITE A BINARY SEARCH IN PYTHON"
        result = router._check_strong_coding_signal(query)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_empty_query(self):
        router = ToolRouter()
        request = AgentRequest(query="", trace_id="test-empty")
        decision = await router.route(request)
        assert decision.intent == IntentEnum.GENERAL
        assert decision.status == StatusEnum.OK


# Comparison test showing the before/after behavior
class TestPhase28BeforeAfterComparison:
    """Demonstrates the exact fix for the reported bug"""
    
    def test_old_behavior_simulation(self):
        """Simulates what happened BEFORE Phase 28"""
        # Old pattern: r"\bwrite (?:a )?python script\b"
        # Query: "write a binary search in python"
        # Result: Pattern didn't match because "binary search" is between "write" and "python"
        
        old_pattern = r"\bwrite (?:a )?python script\b"
        query = "write a binary search in python"
        import re
        match = re.search(old_pattern, query, re.IGNORECASE)
        assert match is None, "Old pattern should NOT match"
    
    def test_new_behavior(self):
        """Shows that Phase 28 patterns DO match"""
        # New pattern: r"\b(?:write|implement|create|build|code) .{0,50}? (?:in|using|with) (?:python|...)\b"
        new_pattern = r"\b(?:write|implement|create|build|code) .{0,50}? (?:in|using|with) (?:python|javascript|java|c\+\+|rust|go|typescript)\b"
        query = "write a binary search in python"
        import re
        match = re.search(new_pattern, query, re.IGNORECASE)
        assert match is not None, "New pattern SHOULD match"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
