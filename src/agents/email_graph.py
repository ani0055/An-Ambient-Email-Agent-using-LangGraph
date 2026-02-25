from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.agents.state import EmailAgentState
from src.nodes.memory import load_memory_node, update_memory_node
from src.nodes.triage import triage_node
from src.nodes.react_agent import react_agent_node
from src.nodes.hitl import hitl_checkpoint_node, should_continue_after_hitl
from src.nodes.execute import execute_action_node


def create_email_agent():
    """Creates the complete email agent with memory and HITL."""
    
    workflow = StateGraph(EmailAgentState)
    
    # Add all nodes
    workflow.add_node("load_memory", load_memory_node)
    workflow.add_node("triage", triage_node)
    workflow.add_node("react_agent", react_agent_node)
    workflow.add_node("hitl_checkpoint", hitl_checkpoint_node)
    workflow.add_node("execute_action", execute_action_node)
    workflow.add_node("update_memory", update_memory_node)
    
    # Entry point
    workflow.set_entry_point("load_memory")
    
    # Load memory → Triage
    workflow.add_edge("load_memory", "triage")
    
    # Triage routing
    def route_after_triage(state: EmailAgentState) -> str:
        decision = state["triage_decision"]
        
        if decision == "ignore":
            return "update_memory_end"
        elif decision == "notify_human":
            return "update_memory_end"
        elif decision == "respond":
            return "react"
        
        return "update_memory_end"
    
    workflow.add_conditional_edges(
        "triage",
        route_after_triage,
        {
            "update_memory_end": "update_memory",
            "react": "react_agent"
        }
    )
    
    # ReAct → HITL
    workflow.add_edge("react_agent", "hitl_checkpoint")
    
    # HITL routing
    def route_after_hitl(state: EmailAgentState) -> str:
        # If requires approval but no decision yet - pause
        if state.get("requires_approval") and not state.get("human_decision"):
            return "pause"
        
        human_decision = state.get("human_decision")
        
        if human_decision in ["approve", "edit"]:
            return "execute"
        else:
            # Denied or no decision
            return "update_memory_end"
    
    workflow.add_conditional_edges(
        "hitl_checkpoint",
        route_after_hitl,
        {
            "pause": END,           # Pause here - wait for human
            "execute": "execute_action",
            "update_memory_end": "update_memory"
        }
    )
    
    # Execute → Update Memory → End
    workflow.add_edge("execute_action", "update_memory")
    workflow.add_edge("update_memory", END)
    
    # Compile with checkpointer
    checkpointer = MemorySaver()
    app = workflow.compile(
        checkpointer=checkpointer,
    )
    
    return app