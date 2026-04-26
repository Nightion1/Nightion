import unittest
import os
import sys

sys.path.insert(0, os.path.abspath('.'))
from memory_core import MemoryCore
from retrieval_governor import RetrievalGovernor

class TestMemoryGovernor(unittest.TestCase):
    def setUp(self):
        # Bind ephemeral memory natively resolving offline SQLite arrays gracefully
        self.db_path = "tests/test_nightion_memory.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
        self.memory = MemoryCore(self.db_path)
        self.governor = RetrievalGovernor(self.memory)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_deduplication_and_confidence_filtering(self):
        # 1. Insert Tool Patterns (1 Low Confidence, 2 High Confidence Dupes)
        self.memory.add_tool_pattern("trace-1", "search", "Use standard DuckDuckGo explicit URLs", success=True, confidence=0.2)
        self.memory.add_tool_pattern("trace-2", "search", "Always use exact duckduckgo parameters natively.", success=True, confidence=0.8)
        self.memory.add_tool_pattern("trace-3", "search", "Always use exact duckduckgo schemas natively.", success=True, confidence=0.9)
        self.memory.add_tool_pattern("trace-4", "browser", "Strict deterministic Playwright DOM selections.", success=True, confidence=0.9)

        # 2. Insert User Constraints
        self.memory.add_preference("trace-5", "Do not modify OS system files blindly.", confidence=0.99)
        
        # 3. Retrieve Governed Constraints
        payload = self.governor.construct_planner_payload()
        
        # Verify deduplication bounds precisely (Should merge trace-2 and trace-3 securely due to Levenshtein > 0.82)
        strategies = payload["known_good_strategies"]
        self.assertEqual(len(strategies), 2, "Failed to dedup exact strings cleanly.")
        
        # Verify Low Confidence dropped
        self.assertNotIn("Use standard DuckDuckGo explicit URLs", strategies)
        
        # Verify Preference Extracted
        self.assertEqual(payload["active_user_constraints"][0], "Do not modify OS system files blindly.")

if __name__ == "__main__":
    unittest.main()
