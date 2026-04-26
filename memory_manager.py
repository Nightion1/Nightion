import json
import os
from typing import List, Dict, Any

class MemoryManager:
    """
    Manages stable agent memory.
    Stores only established facts, repeated corrections, and approved shortcuts.
    NO raw chat noise is stored here to prevent context dilution.
    """
    def __init__(self, storage_path: str = "cache/agent_memory.json"):
        self.storage_path = storage_path
        self._memory: Dict[str, Any] = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"facts": [], "preferences": {}}
        return {"facts": [], "preferences": {}}

    def _save(self):
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self._memory, f, indent=4)

    def add_fact(self, fact: str):
        if fact not in self._memory["facts"]:
            self._memory["facts"].append(fact)
            self._save()

    def get_context(self) -> str:
        if not self._memory.get("facts"):
            return ""
        facts = "\n".join(f"- {fact}" for fact in self._memory["facts"])
        return f"Core System Memory Context:\n{facts}"

    def get_stat_count(self) -> int:
        return len(self._memory.get("facts", []))

    def wipe_all(self):
        self._memory = {"facts": [], "preferences": {}}
        self._save()
