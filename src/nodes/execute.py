from src.agents.state import EmailAgentState
from src.tools.google_tools import get_google_tools


def execute_action_node(state: EmailAgentState) -> EmailAgentState:
    """
    Execute the approved action.
    """
    print("\n⚙️  EXECUTING ACTION")

    pending_action = state.get("pending_action")

    if not pending_action:
        print("   No action to execute")
        return state

    action_type = pending_action.get("action_type")
    action_args = pending_action.get("args", {}).copy()

    # If human edited, update the body
    if state.get("human_decision") == "edit" and state.get("human_feedback"):
        print(f"   📝 Using human-edited version")

        feedback = state.get("human_feedback", {})

        # Update body with human's edit
        if isinstance(feedback, dict):
            edited_body = feedback.get("body_content", "")
        else:
            # If feedback is just a string
            edited_body = str(feedback)

        if edited_body:
            action_args["body"] = edited_body
            # Update preview too
            action_args["draft_preview"] = (
                f"To: {action_args.get('recipient', '')}\n"
                f"Subject: {action_args.get('subject', '')}\n\n"
                f"{edited_body}"
            )

    # Get tools
    tools = get_google_tools()
    tool_dict = {tool.name: tool for tool in tools}

    if action_type in tool_dict:
        print(f"   🛠️  Executing: {action_type}")

        try:
            tool = tool_dict[action_type]
            result = tool.invoke(action_args)

            print(f"   ✓ Action completed successfully")

            return {
                **state,
                "execution_result": result,
                "execution_status": "success"
            }

        except Exception as e:
            error_msg = str(e)
            print(f"   ✗ Execution failed: {error_msg}")

            return {
                **state,
                "execution_result": error_msg,
                "execution_status": "failed"
            }
    else:
        print(f"   ✗ Unknown action type: {action_type}")

        return {
            **state,
            "execution_status": "unknown_action"
        }