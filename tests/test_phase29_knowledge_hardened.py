import pytest
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch
from knowledge_base import KnowledgeBase
from self_trainer import SelfTrainer
from python_sandbox import PythonSandboxWrapper
from verifier import Verifier
from schemas import IntentEnum, ToolResult, StatusEnum, VerificationDecision

@pytest.fixture
def kb_temp():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    kb = KnowledgeBase(db_path=db_path)
    yield kb
    kb.close() # Release file handle for Windows
    if os.path.exists(db_path):
        os.unlink(db_path)

@pytest.fixture
def trainer(kb_temp):
    return SelfTrainer(kb_temp)

@pytest.fixture
def sandbox(kb_temp, trainer):
    return PythonSandboxWrapper(kb_temp, trainer)

# Test 1 — Offline cache
def test_offline_returns_cached(sandbox, trainer, monkeypatch):
    # 1. Ensure binary search is in cache (it's a seed)
    topic = "binary search"
    assert sandbox.kb.lookup(topic) is not None
    
    # 2. Mock offline
    monkeypatch.setattr(SelfTrainer, "is_online", lambda self: False)
    
    # 3. Generate
    output = sandbox.generate_code_solution(topic)
    
    # 4. Assertions
    assert "def binary_search" in output
    assert "Not Found" not in output
    assert "Offline" not in output
    assert "💾 📦 Verified" in output # Status tag check

# Test 2 — Learning test (Dijkstra)
@patch("requests.get")
def test_dijkstra_learned_and_stored(mock_get, sandbox, kb_temp):
    topic = "dijkstra"
    fake_html = """
    <html>
        <body>
            <p>Dijkstra's algorithm finds the shortest path.</p>
            <pre><code>
def dijkstra(graph, start):
    distances = {node: float('inf') for node in graph}
    distances[start] = 0
    return distances
            </code></pre>
        </body>
    </html>
    """
    # Mock online check
    mock_get.return_value.status_code = 200
    mock_get.return_value.text = fake_html
    
    # 1. Ensure not in KB
    assert kb_temp.lookup(topic) is None
    
    # 2. Generate (triggers training)
    output = sandbox.generate_code_solution(topic)
    
    # 3. Assertions
    stored = kb_temp.lookup(topic)
    assert stored is not None
    assert "def dijkstra" in stored["code"]
    assert "⚠️ Auto-Learned" in output
    assert stored["needs_review"] == True

# Test 3 — Anti-stub
@pytest.mark.asyncio
async def test_stub_flagged_as_fail():
    verifier = Verifier()
    stub_output = "print('Execution complete. Sandbox trace verified.')"
    tool_res = ToolResult(
        trace_id="test_trace",
        tool_name="sandbox_python",
        status=StatusEnum.OK,
        output=stub_output,
        execution_time_ms=10
    )
    
    result = await verifier.verify("reverse array", IntentEnum.CODE, tool_res, "test_trace")
    
    # Assertions
    assert result.decision == VerificationDecision.FAIL
    assert "STUB_DETECTED" in result.reason
    assert result.trigger_reroute == False # Rerouting won't fix a logic bug in generator

# Test 4 — Extraction quality scoring
def test_best_code_block_scoring(trainer):
    blocks = [
        "alert('ads!');", # noise
        "def helper(): pass", # small
        "def main():\n    print('long block')\n    return True\n    # keyword: binary search", # match
        "print('Execution complete. Sandbox trace verified.')" # stub
    ]
    topic = "binary search"
    best = trainer._best_code_block(blocks, topic)
    assert "keyword: binary search" in best
    assert "stub" not in best.lower()
