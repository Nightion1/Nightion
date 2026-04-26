import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox import Sandbox
from schemas import StatusEnum

class TestSandboxMalicious(unittest.TestCase):
    def setUp(self):
        # Short timeout to fail fast on infinite loops
        self.sandbox = Sandbox(timeout=1)

    def test_infinite_loop(self):
        code = "while True:\n    pass"
        res = self.sandbox.execute_python(code, "mal1")
        self.assertEqual(res.status, StatusEnum.FAILED)
        self.assertTrue("timed out" in (res.error or ""))

    def test_memory_hog(self):
        # Tries to allocate massive scaling memory to crash host, which should be caught as an Error or Timeout.
        code = "x = []\nwhile True:\n    x.append('A' * 10000000)"
        res = self.sandbox.execute_python(code, "mal2")
        self.assertEqual(res.status, StatusEnum.FAILED)
        self.assertTrue("MemoryError" in (res.error or "") or "timed out" in (res.error or ""))

    def test_import_bypass(self):
        # Naive "import os" check bypass via __import__
        code = "os_module = __import__('os')\nos_module.system('echo Hacked')"
        res = self.sandbox.execute_python(code, "mal3")
        
        # If MVP sandbox is bypassed, it succeeds and prints 'Hacked' (or exits 0)
        # The true hardened sandbox SHOULD block this via ast scanning or strict jail
        # For now, we expect BLOCKED if the regex captures it, else FAILED if we enforce strict AST.
        # This will fail natively pointing out our security flaw if it returns OK.
        self.assertNotEqual(res.status, StatusEnum.OK, "Sandbox allows simple __import__ bypass!")

if __name__ == '__main__':
    unittest.main()
