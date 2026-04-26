import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory_manager import MemoryManager

class TestMemory(unittest.TestCase):
    def setUp(self):
        # Setup specific temp db for testing to avoid overwriting prod cache
        self.mem = MemoryManager("test_cache/agent_memory.json")
        self.mem.wipe_all()

    def tearDown(self):
        self.mem.wipe_all()
        if os.path.exists("test_cache/agent_memory.json"):
            os.remove("test_cache/agent_memory.json")
        if os.path.exists("test_cache"):
            os.rmdir("test_cache")

    def test_add_and_wipe(self):
        self.assertEqual(self.mem.get_stat_count(), 0)
        
        self.mem.add_fact("The user prefers precise answers.")
        self.assertEqual(self.mem.get_stat_count(), 1)
        self.assertTrue("precise answers" in self.mem.get_context())
        
        # Test deduplication
        self.mem.add_fact("The user prefers precise answers.")
        self.assertEqual(self.mem.get_stat_count(), 1)

        self.mem.wipe_all()
        self.assertEqual(self.mem.get_stat_count(), 0)

if __name__ == '__main__':
    unittest.main()
