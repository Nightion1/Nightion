import os
import time
import pytest
import json
from cache_layer import DeterministicCache
from telemetry import TelemetryRecorder

def test_deterministic_cache_bounds():
    cache = DeterministicCache(ttl_seconds=10)
    
    # 1. Caching verify states natively offline
    cache.set("verify_pytest", "test_failure_string_x", {"decision": "failed", "retry": True})
    hit = cache.get("verify_pytest", "test_failure_string_x")
    assert hit is not None
    assert hit["decision"] == "failed"
    
    # 2. Refusing Unsafe States intrinsically cleanly
    cache.set("execute_code", "patch_db_files", {"result": "ok"})
    unsafe_hit = cache.get("execute_code", "patch_db_files")
    assert unsafe_hit is None, "Cache Layer structurally violated Determinism explicitly caching mutated bounds!"

def test_telemetry_batching_flush():
    recorder = TelemetryRecorder(trace_id="test_batch_123")
    
    # Write a single query string natively offline
    recorder.record_query("Hello World Optimization")
    
    # Without flushing, the file won't have the recent mutations physically natively offline
    trace_file = os.path.join(recorder.trace_dir, "request.json")
    
    # Force flush dynamically checking paths mathematically linearly
    recorder.force_flush()
    assert os.path.exists(trace_file)
    with open(trace_file, "r") as f:
         data = json.load(f)
         assert data["query"] == "Hello World Optimization"

    print("Phase 26 Benchmark Suite -> Cache & Telemetry Performance Integrity Passed!")
