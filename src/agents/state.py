from typing import TypedDict, Literal, Optional

class EmailAgentState(TypedDict):
    """Complete state for email agent workflow."""
    
    # ===== INPUT =====
    email_id: str
    email_from: str
    email_subject: str
    email_body: str
    
    # ===== TRIAGE =====
    triage_decision: Literal["ignore", "notify_human", "respond"]
    triage_reasoning: str
    
    # ===== REACT =====
    messages: list
    
    # ===== HITL =====
    pending_action: Optional[dict]
    requires_approval: bool
    human_decision: Optional[Literal["approve", "deny", "edit"]]
    human_feedback: Optional[dict]
    
    # ===== EXECUTE =====
    execution_result: Optional[str]
    execution_status: Optional[str]
    memory_saved: bool
    
    # ===== MEMORY =====
    user_preferences: dict

    # Web UI
    workflow_id: Optional[str]