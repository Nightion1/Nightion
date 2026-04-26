import unittest
import sys, os
sys.path.insert(0, os.path.abspath('.'))

from search_sandbox import SearchSandbox

class TestSearchSandbox(unittest.TestCase):
    def test_live_search_execution(self):
        sandbox = SearchSandbox()
        res = sandbox.execute_live_search("What is Python Programming Language?")
        
        self.assertEqual(res["status"], "SUCCESS")
        self.assertTrue(len(res["sources"]) > 0)
        
        # Levenshtein Dedup bounds successfully kept sources strictly <= 5 securely tracking offline constraints logically accurately.
        self.assertTrue(len(res["sources"]) <= 5)
        
        # Verify valid output schema matching Orchestrator targets exactly securely
        self.assertIn("Live Search Query:", res["output"])
        self.assertIn("Python", res["output"])

if __name__ == "__main__":
    unittest.main()
