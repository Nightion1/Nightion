import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from guards import evaluate_action, ActionRisk

class TestAppControlGuard(unittest.TestCase):
    def test_destructive_action(self):
        guard = evaluate_action("delete", "file.txt", {})
        self.assertFalse(guard.allowed)
        self.assertEqual(guard.risk_level, ActionRisk.CRITICAL)

    def test_safe_action(self):
        guard = evaluate_action("scroll", "page", {})
        self.assertTrue(guard.allowed)
        self.assertEqual(guard.risk_level, ActionRisk.SAFE)

    def test_overwrite_action(self):
        guard = evaluate_action("overwrite", "sys.conf", {})
        self.assertFalse(guard.allowed)
        self.assertEqual(guard.risk_level, ActionRisk.CRITICAL)

    def test_open_action(self):
        guard = evaluate_action("open_app", "calculator", {})
        self.assertTrue(guard.allowed)
        self.assertEqual(guard.risk_level, ActionRisk.MODERATE)

if __name__ == '__main__':
    unittest.main()
