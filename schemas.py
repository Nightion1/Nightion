from pydantic import BaseModel, Field, model_validator
from typing import List, Optional, Any, Dict
from enum import Enum
from datetime import datetime, timezone

# --- Enums ---
class StatusEnum(str, Enum):
    OK = "ok"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_CLARIFICATION = "needs_clarification"

class NextActionEnum(str, Enum):
    RESPOND = "respond"
    RETRY = "retry"
    ASK_USER = "ask_user"
    VERIFY = "verify"
    RUN_TOOL = "run_tool"

class IntentEnum(str, Enum):
    GREETING = "greeting"
    DSA = "dsa"
    CODE = "code"
    APP_CONTROL = "app_control"
    BROWSER_AUTOMATION = "browser_automation"
    GENERAL = "general"
    DELEGATE = "delegate"

class AgentRole(str, Enum):
    PRIMARY_ORCHESTRATOR = "primary_orchestrator"
    RESEARCH_SPECIALIST = "research_specialist"
    CODE_EXECUTOR = "code_executor"

class TaskResultStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    INCOMPLETE = "incomplete"
    CONFLICTING = "conflicting"



# --- Structured Sub-Models ---
class SourceItem(BaseModel):
    title: str
    url: str  # plain str — HttpUrl caused Pydantic v2 to return HttpUrl objects, breaking .lower()/.startswith() calls
    snippet: Optional[str] = None

class Message(BaseModel):
    role: str
    content: str

# --- Frontend specific schemas ---
class FrontendChatRequest(BaseModel):
    message: str
    use_rag: bool = True
    session_id: str = "default_session"

class FrontendLearnRequest(BaseModel):
    text: str
    source: str = "user"

class FrontendExecuteRequest(BaseModel):
    code: str
    timeout: int = 10

# --- Internal Module API Contracts ---
class TaskProposal(BaseModel):
    task_id: str
    parent_trace_id: str
    role: AgentRole
    objective: str
    allowed_tools: List[str]
    context_slice: str
    success_criteria: str
    timeout_seconds: int = 30

class TaskResultNode(BaseModel):
    task_id: str
    trace_id: str
    status: TaskResultStatus
    result_payload: str
    confidence: float
    error_context: Optional[str] = None
    
# --- Phase 23: Mission Execution Layer ---

class MissionClass(str, Enum):
    RESEARCH = "research"
    CODING = "coding"
    WEB_SCRAPING = "web_scraping"
    LOCAL_ADMIN = "local_admin"
    RECOVERY = "recovery"
    MAINTENANCE = "maintenance"

class OutcomeScore(BaseModel):
    completion_status: StatusEnum
    accuracy_score: float  # 0.0 - 1.0 (Verifier Evaluated)
    latency_ms: float
    retry_depth: int
    gate_reason: Optional[str] = None  # Populates if the Human Approval Gate blocked it

class MissionProfile(BaseModel):
    mission_id: str
    mission_class: MissionClass
    objective: str
    success_criteria: str
    
class MissionNormalizedResult(BaseModel):
    """ The canonical output enforcing unified cross-mission tracking cleanly avoiding disparate array bounds uniquely. """
    profile_id: str
    score: OutcomeScore
    final_output: str
    trace_id: str
    tools_used: List[str]

# --- Phase 24: Coding Sub-Task Schemas ---
class CodingTaskType(str, Enum):
    BUGFIX = "bugfix"
    IMPLEMENT_FEATURE = "implement_feature"
    WRITE_TESTS = "write_tests"
    REFACTOR = "refactor"
    DEBUG_FAILURE = "debug_failure"

class CodingMissionProfile(MissionProfile):
    """ Restricts physical footprints evaluating exact Artifact limitations avoiding uncontrolled sprawl cleanly. """
    task_type: CodingTaskType
    target_files: List[str]     # Files the agent can modify
    test_suite_cmd: str         # The strict programmatic verifier loop hook
    max_patch_size_bytes: int = 15000  # Artifact Limit 
    max_retries: int = 3
    
class PatchExecutionContract(BaseModel):
    target_file: str
    search_string: str
    replacement_string: str

# --- Phase 25: Domain Knowledge Governance ---
class DomainPack(BaseModel):
    """ Rigidly versioned Domain Policies dictating context scopes filtering unstructured memories elegantly reliably offline. """
    pack_id: str
    mission_class: MissionClass
    version: int          # Monotonic integer scale natively
    ruleset: str          # Markdown serialized domain parameters cleanly offline
    source_author: str
    confidence: float     # 0.0 - 1.0 explicit Trust Score linearly
    last_verified: float  # Timestamp explicit bounds natively
    is_authoritative: bool = False # Overrides standard `newest-wins` fallback limits globally

# --- Phase 27: Unattended Proactive Background Scheduling ---
class TaskQueueStatus(str, Enum):
    PENDING = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"

class QueuedMission(BaseModel):
    queue_id: str
    mission_class: MissionClass
    target_profile: str     # Bound payload parameters gracefully
    trigger_time_s: float   # Epoch Chron trigger limit Native
    status: TaskQueueStatus
    lease_expires_at: float = 0.0 # Bounded Unattended runtime thresholds completely

class AgentRequest(BaseModel):
    trace_id: str
    query: str
    history: List[Message] = Field(default_factory=list)
    retry_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class RouterDecision(BaseModel):
    trace_id: str
    intent: IntentEnum
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    status: StatusEnum = StatusEnum.OK
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ToolResult(BaseModel):
    trace_id: str
    tool_name: str
    status: StatusEnum
    output: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: int = Field(ge=0)
    requires_confirmation: bool = False
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VerificationDecision(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"

class ThoughtSchema(BaseModel):
    understanding: str
    plan: str
    steps: list[str]
    uncertainty: float = Field(ge=0.0, le=1.0)
    requires_tools: bool
    context_strategy: str = "Unknown"

class VerificationResult(BaseModel):
    trace_id: str
    decision: VerificationDecision
    status: StatusEnum
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    counterexample: Optional[str] = None
    suggested_fix: Optional[str] = None
    severity: Optional[str] = "low"  # low, medium, high
    trigger_reroute: bool = False
    suggested_intent: Optional[IntentEnum] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode='after')
    def check_suggested_fix(self):
        if self.decision in [VerificationDecision.FAIL, VerificationDecision.UNCERTAIN] and not self.suggested_fix:
            raise ValueError('suggested_fix must be provided when decision is FAIL or UNCERTAIN.')
        return self

class AgentResponse(BaseModel):
    trace_id: str
    status: StatusEnum
    result: str
    confidence: float = Field(ge=0.0, le=1.0)
    sources: Optional[List[SourceItem]] = Field(default_factory=list)
    error: Optional[str] = None
    next_action: NextActionEnum = NextActionEnum.RESPOND
    tool_calls: Optional[List[str]] = Field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
