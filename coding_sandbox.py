import os
import subprocess
import ast
from typing import List, Tuple
from schemas import PatchExecutionContract

class CodingSandbox:
    """ Strict patch-based execution isolating REPL generic evaluations cleanly preventing Workspace sprawl offline perfectly Native. """
    
    def __init__(self, allowed_files: List[str], max_patch_size: int = 15000):
        # Convert to absolute mapped pathways safely offline
        self.allowed_paths = [os.path.abspath(f) for f in allowed_files]
        self.max_patch_size = max_patch_size

    def _verify_boundary(self, target_file: str) -> bool:
        """ Ensures SubAgents cannot navigate above bounded scopes cleanly natively offline. """
        abs_target = os.path.abspath(target_file)
        return any(abs_target == allowed for allowed in self.allowed_paths)

    def apply_patch(self, patch: PatchExecutionContract) -> Tuple[bool, str]:
        """ Replaces arbitrary code runs with exact mechanical File Modifiers structurally predictably strictly natively. """
        if not self._verify_boundary(patch.target_file):
             return False, f"SECURITY FAULT: File {patch.target_file} falls outside bounded Coding Mission allowed scopes natively offline."
             
        patch_size = len(patch.replacement_string.encode('utf-8'))
        if patch_size > self.max_patch_size:
             return False, f"ARTIFACT LIMIT EXCEEDED: Patch size ({patch_size} bytes) exceeds limit ({self.max_patch_size} bytes) smoothly offline."
             
        if not os.path.exists(patch.target_file):
             return False, f"EXECUTION FAULT: Target bounded file {patch.target_file} missing securely offline."
             
        with open(patch.target_file, "r", encoding="utf-8") as f:
             content = f.read()

        if patch.search_string not in content:
             return False, "EXECUTION FAULT: Target Context missing evaluating string matches securely offline."
             
        patched_content = content.replace(patch.search_string, patch.replacement_string, 1)
        
        # AST Validation BEFORE saving
        if patch.target_file.endswith(".py"):
             try:
                 ast.parse(patched_content)
             except SyntaxError as e:
                 return False, f"AST LINTER FAILED: Patch broke syntax tree - {e}"

        with open(patch.target_file, "w", encoding="utf-8") as f:
             f.write(patched_content)
             
        return True, "Patch applied structurally stably offline."

    def run_tests(self, test_cmd: str, timeout: int = 15) -> Tuple[bool, str]:
        """ Forces mechanical Pytest feedback looping explicitly handling generic programmatic Verifier dependencies stably intuitively offline. """
        try:
             # Timeout boundaries implicitly preventing arbitrary lock-ups gracefully offline
             result = subprocess.run(test_cmd.split(), capture_output=True, text=True, timeout=timeout)
             if result.returncode == 0:
                 return True, "All tests passed natively."
             else:
                 return False, f"TEST FAILED:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        except subprocess.TimeoutExpired:
             return False, f"TEST TIMEOUT: Native suite exceeded {timeout}s budget natively offline."
