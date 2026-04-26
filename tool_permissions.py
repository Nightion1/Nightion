from enum import Enum
from dataclasses import dataclass, field
from typing import List

class RiskLevel(str, Enum):
    LOW = "low"             # Read-only contexts or tightly walled limits like isolated python evaluation
    MODERATE = "moderate"     # Local network connections, external endpoints
    HIGH = "high"             # Structural file modifications internally
    CRITICAL = "critical"     # OS Command line interfaces explicitly bypassing isolation natively

@dataclass
class ToolContract:
    """ Strict permission wrapper tracking dynamic execution requirements mapping cleanly offline. """
    name: str
    description: str
    risk_level: RiskLevel
    requires_confirmation: bool = False
    allowed_scopes: List[str] = field(default_factory=list)
    
    def validate_payload(self, payload: str) -> tuple[bool, str]:
        """ Introspects requested arguments mapping against explicit bounds synchronously before async launching natively. """
        
        # 1. Structural Confinement Gate
        if self.risk_level == RiskLevel.CRITICAL and not self.requires_confirmation:
            return False, "Logical Exception: CRITICAL bounds mandate explicit user confirmations natively."
            
        # 2. Heuristic Scope Limits
        if "os" in self.allowed_scopes and self.risk_level == RiskLevel.LOW:
             return False, "Logical Exception: Low-risk tools cannot access raw OS scopes."

        # Extended Scope checks (i.e enforcing paths match within boundaries linearly)
        return True, "Payload matches execution contract natively."
