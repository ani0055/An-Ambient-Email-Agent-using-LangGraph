from src.agents.state import EmailAgentState
from typing import Literal

# Define which tools are "dangerous" and require approval
DANGEROUS_TOOLS = [
    "send_email_reply",  # Sending emails - REQUIRES APPROVAL
    "schedule_meeting",  # Creating calendar events - REQUIRES APPROVAL
    "delete_email",      # Deleting emails - REQUIRES APPROVAL
    "forward_email"      # Forwarding emails - REQUIRES APPROVAL
]

# Safe tools that run automatically
SAFE_TOOLS = [
    "check_calendar",    # Just reads data
    "search_past_emails", # Just reads data
    "draft_email_reply"  # Just creates draft, doesn't send
]


def hitl_checkpoint_node(state: EmailAgentState) -> EmailAgentState:
    """
    Human-in-the-Loop checkpoint.
    
    Pauses workflow if a dangerous action is pending.
    """
    print("\n🚦 HITL CHECKPOINT")
    
    # Check if there's a pending action
    pending_action = state.get("pending_action")
    
    if not pending_action:
        print("   ℹ️  No pending action - continuing")
        return {
            **state,
            "requires_approval": False
        }
    
    action_type = pending_action.get("action_type")
    
    # Check if action is dangerous
    if action_type in DANGEROUS_TOOLS:
        print(f"   ⚠️  DANGEROUS ACTION: {action_type}")
        print(f"   🛑 PAUSING for human approval")
        
        # Show preview
        args = pending_action.get("args", {})
        if "draft_preview" in args:
            print(f"\n   📧 Email Preview:")
            print(f"   To: {args.get('recipient', 'N/A')}")
            print(f"   Subject: {args.get('subject', 'N/A')}")
            print(f"   {'-'*64}")
            preview = args.get('draft_preview', '')[:200]
            print(f"   {preview}...")
            print(f"   {'-'*64}")
        
        return {
            **state,
            "requires_approval": True
        }
    
    # Safe action - auto-approve
    print(f"   ✓ Safe action: {action_type}")
    print(f"   ✓ Auto-approved - continuing")
    
    return {
        **state,
        "requires_approval": False,
        "human_decision": "approve"
    }


def should_continue_after_hitl(state: EmailAgentState) -> Literal["execute", "end", "wait"]:
    """
    Routing function after HITL checkpoint.
    
    Returns:
        - "wait": Paused, waiting for human input
        - "execute": Human approved, continue
        - "end": Human denied, stop workflow
    """
    
    # Check if we're waiting for approval
    if state.get("requires_approval") and not state.get("human_decision"):
        # Still waiting for human input - pause here
        return "wait"
    
    human_decision = state.get("human_decision")
    
    if human_decision == "approve":
        return "execute"
    elif human_decision == "edit":
        return "execute"  # Execute with edited version
    else:  # deny or None
        return "end"