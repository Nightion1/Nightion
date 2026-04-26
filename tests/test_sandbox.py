import unittest
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sandbox import Sandbox
from schemas import StatusEnum

class TestSandbox(unittest.TestCase):
    def setUp(self):
        self.sandbox = Sandbox(timeout=2)

    def test_basic_execution(self):
        code = "print('Hello World')"
        res = self.sandbox.execute_python(code, "abc")
        self.assertEqual(res.status, StatusEnum.OK)
        self.assertEqual(res.output, "Hello World")

    def test_blocked_imports(self):
        code = "import os\nos.system('dir')"
        res = self.sandbox.execute_python(code, "abc")
        self.assertEqual(res.status, StatusEnum.BLOCKED)
        self.assertTrue("Security Exception" in (res.error or ""))

    def test_timeout(self):
        # time is allowed, using it to trigger timeout
        code = "import time\ntime.sleep(3)"
        res = self.sandbox.execute_python(code, "abc")
        self.assertEqual(res.status, StatusEnum.FAILED)
        self.assertTrue("timed out" in (res.error or ""))

    def test_runtime_error(self):
        code = "x = 1 / 0"
        res = self.sandbox.execute_python(code, "abc")
        self.assertEqual(res.status, StatusEnum.FAILED)
        self.assertTrue("ZeroDivisionError" in (res.error or ""))

if __name__ == '__main__':
    unittest.main()
