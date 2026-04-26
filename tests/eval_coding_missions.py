import os
import pytest
from coding_sandbox import CodingSandbox
from schemas import PatchExecutionContract

TEST_PYTHON_FILE = "dummy_script.py"

def setup_function():
    with open(TEST_PYTHON_FILE, "w", encoding="utf-8") as f:
        f.write("def add(a, b):\n    return a - b\n")

def teardown_function():
    if os.path.exists(TEST_PYTHON_FILE): os.remove(TEST_PYTHON_FILE)

def test_coding_sandbox_bounds_and_patching():
    sandbox = CodingSandbox(allowed_files=[TEST_PYTHON_FILE], max_patch_size=1000)
    
    # 1. Reject Out of Bounds file
    bad_patch = PatchExecutionContract(target_file="unauthorized_file.py", search_string="", replacement_string="")
    success, msg = sandbox.apply_patch(bad_patch)
    assert not success, "Sandbox failed to bound external files natively!"
    assert "falls outside bounded Coding Mission allowed scopes" in msg

    # 2. Reject arbitrary AST breakers
    broken_patch = PatchExecutionContract(
        target_file=TEST_PYTHON_FILE, 
        search_string="return a - b", 
        replacement_string="return a - b def )(" # Syntax Error
    )
    success, msg = sandbox.apply_patch(broken_patch)
    assert not success, "Sandbox blindly applied structurally broken Abstract Syntax Trees offline!"
    assert "AST LINTER FAILED" in msg
    
    # 3. Apply Clean Patch
    clean_patch = PatchExecutionContract(
        target_file=TEST_PYTHON_FILE,
        search_string="return a - b",
        replacement_string="return a + b"
    )
    success, msg = sandbox.apply_patch(clean_patch)
    assert success, "Clean programmatic Patch failed native Sandbox checks unexpectedly smoothly."
    
    # Verify exact target was rewritten gracefully
    with open(TEST_PYTHON_FILE, "r") as f:
        assert "return a + b" in f.read(), "File writes dropped mapping AST limits poorly natively."

    print("Phase 24 Test Suite -> Coding Sandbox Contracts verified successfully natively offline!")
