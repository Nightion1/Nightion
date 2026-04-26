from enum import Enum
from typing import List, Optional

class ActionRisk(str, Enum):
    SAFE = "safe"           # scroll, typing in safe context, view page
    MODERATE = "moderate"   # opening an app, external API call
    CRITICAL = "critical"   # delete, close, overwrite, submit, install

class GuardResult:
    def __init__(self, action_name: str, allowed: bool, risk_level: ActionRisk, reason: Optional[str] = None):
        self.action_name = action_name
        self.allowed = allowed
        self.risk_level = risk_level
        self.reason = reason

def evaluate_action(action_name: str, target: str, payload: dict) -> GuardResult:
    """
    Evaluates whether an application control action is allowed to proceed immediately,
    or if it triggers a confirmation gate.
    """
    unsafe_keywords = ["delete", "rm", "rmdir", "format", "drop", "uninstall", "overwrite"]
    
    # 1. Destructive keyword check
    action_str = f"{action_name} {target}".lower()
    if any(kw in action_str for kw in unsafe_keywords):
        return GuardResult(action_name, False, ActionRisk.CRITICAL, "Destructive keyword detected.")
        
    # 2. Risk classification
    if action_name in ["scroll", "mouse_move", "read"]:
        return GuardResult(action_name, True, ActionRisk.SAFE)
        
    if action_name in ["open_app", "click"]:
        return GuardResult(action_name, True, ActionRisk.MODERATE)
        
    if action_name in ["close_app", "write_file", "submit_form"]:
        return GuardResult(action_name, False, ActionRisk.CRITICAL, "Action requires explicit user confirmation.")
        
    return GuardResult(action_name, False, ActionRisk.CRITICAL, "Unknown action pattern blocked by default.")

def pre_check_query(query: str) -> bool:
    """ 
    Absolute Global Safety Pre-Check.
    Runs BEFORE reasoning or routing to prevent destructive intents from falling through 
    to GENERAL or CODE and bypassing tool-specific gates.
    """
    destructive_patterns = [
        "delete", "format", "rm -rf", "drop table", "mkfs", "wipe", "uninstall"
    ]
    query_lower = query.lower()
    for pattern in destructive_patterns:
        if pattern in query_lower:
            return False # Blocked
    return True # Safe
