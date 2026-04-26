import random
import difflib
from typing import List, Optional, Union, Dict, Any
from schemas import DomainPack, MissionClass
from domain_governance import DomainGovernanceDb
from memory_core import MemoryCore

class RetrievalGovernor:
    """ Filters Domains strictly by Mission bounds explicitly extracting Newest Verified schemas correctly structurally natively. """
    
    def __init__(self, db: Optional[Union[DomainGovernanceDb, MemoryCore]] = None, governance_db: Optional[DomainGovernanceDb] = None):
        target_db = db or governance_db
        if isinstance(target_db, MemoryCore):
            self.memory = target_db
            self.gov_db = DomainGovernanceDb()
        elif isinstance(target_db, DomainGovernanceDb):
            self.gov_db = target_db
            self.memory = MemoryCore()
        else:
            self.gov_db = DomainGovernanceDb()
            self.memory = MemoryCore()

    def retrieve_domain_context(self, active_mission: MissionClass, pack_id: str) -> str:
        """
        Phase 25 Rule: Domain-Before-Semantic.
        We completely filter to Mission limits extracting the explicit ruleset natively bypassing random relevance noise seamlessly.
        """
        active_pack = self.gov_db.get_active_pack(active_mission, pack_id)
        if not active_pack:
             # Minimal global fallback
             return f"No Active Domain Packs bound to {active_mission.value}. Adhere strictly to System Policies."
             
        # Format injected bounds linearly wrapping Knowledge Context safely tracking native bounds natively offline
        return f"""
============= DOMAIN GOVERNANCE: {active_pack.pack_id} =============
Mission Class: {active_pack.mission_class.value.upper()}
Version: v{active_pack.version} (Authoritative: {active_pack.is_authoritative})
Confidence: {active_pack.confidence}

RULES:
{active_pack.ruleset}
====================================================================
"""

    def construct_planner_payload(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "known_good_strategies": [],
            "active_user_constraints": [],
            "verified_facts": [],
            "session_history": []
        }
        
        if session_id:
            payload["session_history"] = self.memory.fetch_session_history(session_id, limit=10)

        for pref in self.memory.fetch_active_preferences():
            if pref["confidence"] >= 0.8:
                payload["active_user_constraints"].append(pref["constraint_rule"])
                
        facts = self.memory.fetch_all_facts(only_injected=True)
        for fact in facts:
            # Assuming injected facts are inherently "verified" or have sufficient confidence
            payload["verified_facts"].append(fact["fact_statement"])

        patterns = self.memory.fetch_recent_patterns()
        strategies = []
        for p in patterns:
            if p["success"] and p["confidence"] >= 0.8:
                desc = p["strategy_description"]
                is_dupe = False
                for existing in strategies:
                    if self._similarity(desc, existing) > 0.82:
                        is_dupe = True
                        break
                if not is_dupe:
                    strategies.append(desc)
                    
        payload["known_good_strategies"] = strategies
        return payload

    def _similarity(self, a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
