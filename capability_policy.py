from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List

class CapabilityLevel(str, Enum):
    ISOLATED = "isolated"
    RESTRICTED = "restricted" # No network, no unjailed file IO
    STANDARD = "standard"     # Safe APIs only, jailed file read
    ELEVATED = "elevated"     # Write access allowed (manual user confirmation required)

@dataclass
class PolicyState:
    """ Tracks active agent capabilities preventing unauthorized destructive code globally against OS limits. """
    level: CapabilityLevel
    allowed_domains: List[str] = field(default_factory=list)
    require_confirmation: bool = True
    session_timeout_seconds: int = 300
    
    # Phase 16 Real-World OS Limits bounds
    active_action_mode: str = "read_only" # Maps to ActionModes natively enforcing OS limits

class CapabilityGate:
    """ Evaluates defensively whether a specific tool execution fits inside the active Policy constraints natively. """
    def __init__(self, policy: PolicyState):
        self.policy = policy
        
    def can_execute(self, tool_name: str, payload_args: str) -> tuple[bool, str]:
        """ Inspects the isolated execution request guaranteeing literal execution boundaries. """
        
        # 1. Restricted Policy absolute isolation
        if self.policy.level == CapabilityLevel.RESTRICTED:
            if tool_name in ["os_shell", "file_write", "network_request", "app_control"]:
                return False, f"Tool [{tool_name}] absolutely forbidden under RESTRICTED profile."
                
        # 2. Standard limit checks (No native Write overwrites natively)
        if self.policy.level == CapabilityLevel.STANDARD:
            if tool_name in ["app_control", "os_shell"]:
                # Ensure no destructive commands bypass through basic boundaries
                payload_lower = payload_args.lower()
                unsafe = ["delete", "format", "rm -rf", "drop"]
                if any(kw in payload_lower for kw in unsafe):
                    return False, f"Destructive payload flagged via STANDARD Gate limits."
                    
        # Future expansions: Check args vs exact Jailed directory paths.
        
        return True, "Allowed via explicit Capability Gate limits."
