import json
import os
import atexit
from datetime import datetime, timezone
from typing import Dict, Any, List

class TelemetryRecorder:
    """ Phase 26 Batched Telemetry dropping synchronous I/O lags mathematically terminating writes smoothly safely natively. """
    
    # Global flush registry handling Phase 26 atexit Flush-Before-Exit constraints mathematically
    _active_recorders = []
    
    @classmethod
    def _global_flush(cls):
        for recorder in cls._active_recorders:
            recorder.force_flush()

    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        self.log_dir = os.path.join(os.path.dirname(__file__), "logs")
        self.trace_dir = os.path.join(self.log_dir, self.trace_id)
        os.makedirs(self.trace_dir, exist_ok=True)
        self.index_file = os.path.join(self.log_dir, "index.json")
        
        self.execution_log_path = os.path.join(self.trace_dir, "tool_runs.json")
        
        # Buffer to eliminate disk spin locks implicitly natively offline
        self.buffer: Dict[str, Any] = {}
        self.flush_threshold = 5
        self._mutations_since_flush = 0
        
        TelemetryRecorder._active_recorders.append(self)
        self._update_index()

    def force_flush(self):
        """ Hard physical sync executing exactly batched traces natively dropping limits smoothly. """
        if not self.buffer: return
        try:
             for filepath, data in self.buffer.items():
                 with open(filepath, "w") as f:
                     json.dump(data, f, indent=4)
             self.buffer.clear()
             self._mutations_since_flush = 0
        except Exception as e:
             print(f"TELEMETRY FAULT: Batched sync failed natively offline - {e}")

    def _buffered_write(self, filepath: str, data: Any):
        self.buffer[filepath] = data
        self._mutations_since_flush += 1
        if self._mutations_since_flush >= self.flush_threshold:
             self.force_flush()

    def _read_list(self, filepath: str) -> List[Any]:
        if filepath in self.buffer: return self.buffer[filepath]
        if not os.path.exists(filepath): return []
        with open(filepath, "r") as f:
            try: return json.load(f)
            except json.JSONDecodeError: return []

    def _update_index(self):
        index_data = self._read_list(self.index_file)
        if not any(entry.get("trace_id") == self.trace_id for entry in index_data):
            index_data.append({
                "trace_id": self.trace_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "pending_execution"
            })
            self._buffered_write(self.index_file, index_data)

    def _update_index_status(self, final_status: str, query: str = ""):
        index_data = self._read_list(self.index_file)
        for entry in index_data:
            if entry.get("trace_id") == self.trace_id:
                entry["status"] = final_status
                if query: entry["query"] = query
                break
        self._buffered_write(self.index_file, index_data)

    def record_query(self, query: str):
        self._buffered_write(os.path.join(self.trace_dir, "request.json"), {"query": query, "timestamp": datetime.now(timezone.utc).isoformat()})
        self._update_index_status("running", query=query[:100])

    def record_routing(self, decision: Any):
        self._buffered_write(os.path.join(self.trace_dir, "router.json"), {
            "intent": decision.intent.value,
            "confidence": decision.confidence,
            "reasoning": decision.reasoning
        })

    def record_cognition(self, thought: Any, policy_state: dict):
        plan_path = os.path.join(self.trace_dir, "plan.json")
        history = self._read_list(plan_path)
        history.append({
            "understanding": thought.understanding,
            "plan": thought.plan,
            "steps": thought.steps,
            "uncertainty": thought.uncertainty,
            "requires_tools": thought.requires_tools,
            "context_strategy": thought.context_strategy,
            "policy_state": policy_state
        })
        self._buffered_write(plan_path, history)

    def record_execution_step(self, step_desc: str, tool_res: Any, verification: Any, latency_ms: float = 0.0):
        runs = self._read_list(self.execution_log_path)
        from config import config
        target_budget = config.SEARCH_TIMEOUT * 1000
        if latency_ms > target_budget:
            print(f"[LATENCY BUDGET WARNING] {step_desc} exceeded deterministic {target_budget}ms bound natively: {latency_ms}ms")
            
        runs.append({
            "step": step_desc,
            "tool_output": tool_res.output if tool_res else None,
            "verification_decision": verification.decision.value if verification else None,
            "verification_reason": verification.reason if verification else None,
            "suggested_fix": verification.suggested_fix if verification else None,
            "latency_ms": latency_ms
        })
        self._buffered_write(self.execution_log_path, runs)

    def record_final_response(self, response: Any):
        self._buffered_write(os.path.join(self.trace_dir, "response.json"), {
            "status": response.status.value,
            "result": response.result,
            "confidence": response.confidence,
            "metadata": response.metadata
        })
        self._update_index_status(response.status.value)
        self.force_flush()

atexit.register(TelemetryRecorder._global_flush)
