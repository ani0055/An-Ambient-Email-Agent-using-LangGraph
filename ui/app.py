from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import asyncio
import json
import uuid
import sys 
from typing import Dict
from datetime import datetime
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.integrations.gmail_auth import authenticate_google_services
from src.tools.google_tools import initialize_tools
from src.agents.email_graph import create_email_agent


background_loop = None

async def _set_event(event):
    """Helper to set an event from a coroutine."""
    event.set()

app = FastAPI(title="Email Agent HITL Interface")

templates = Jinja2Templates(directory="ui/templates")

# Store workflow states and websocket connections
pending_approvals: Dict[str, dict] = {}
approval_events: Dict[str, asyncio.Event] = {}
approval_decisions: Dict[str, dict] = {}
websocket_connections: list = []

# Initialize agent
agent = None
gmail_service = None
calendar_service = None


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    global agent, gmail_service, calendar_service
    
    print("\n🚀 Starting Email Agent HITL Server...")
    
    try:
        # ✅ Initialize memory system FIRST
        from src.nodes.memory import initialize_memory
        initialize_memory(db_path="agent_memory.db")
        print("✅ Memory initialized")
        
        gmail_service, calendar_service = authenticate_google_services()
        initialize_tools(gmail_service, calendar_service)
        agent = create_email_agent()
        print("✅ Agent initialized successfully")
    except Exception as e:
        print(f"⚠️  Warning: Could not initialize services: {e}")
        print("   You can still test the UI manually")


@app.get("/")
async def get_ui(request: Request):
    """Serve the main HITL interface."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates."""
    await websocket.accept()
    websocket_connections.append(websocket)
    
    try:
        # Send any pending approvals to new connection
        for workflow_id, approval in pending_approvals.items():
            await websocket.send_json({
                "type": "approval_request",
                "data": approval
            })
        
        # Keep connection alive and listen for decisions
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "human_decision":
                workflow_id = message["workflow_id"]
                decision = message["decision"]
                edited_content = message.get("edited_content", "")
                
                print(f"\n👤 Human decision received:")
                print(f"   Workflow: {workflow_id}")
                print(f"   Decision: {decision}")
                
                # Store the decision
                approval_decisions[workflow_id] = {
                    "decision": decision,
                    "edited_content": edited_content,
                    "timestamp": datetime.now().isoformat()
                }
                
                # Signal the waiting workflow
                if workflow_id in approval_events:
                    if background_loop:
                        # Schedule the set on the background loop
                        asyncio.run_coroutine_threadsafe(
                            _set_event(approval_events[workflow_id]),
                            background_loop
                        )
                        print(f"   🔔 Scheduled event set for {workflow_id}")
                    else:
                        # Fallback (should not happen)
                        approval_events[workflow_id].set()
                
                # Remove from pending
                if workflow_id in pending_approvals:
                    del pending_approvals[workflow_id]
                
                # Notify all clients
                await broadcast_message({
                    "type": "decision_recorded",
                    "workflow_id": workflow_id,
                    "decision": decision
                })
    
    except WebSocketDisconnect:
        websocket_connections.remove(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        if websocket in websocket_connections:
            websocket_connections.remove(websocket)


async def broadcast_message(message: dict):
    """Send message to all connected clients."""
    disconnected = []
    for ws in websocket_connections:
        try:
            await ws.send_json(message)
        except Exception:
            disconnected.append(ws)
    
    for ws in disconnected:
        websocket_connections.remove(ws)


@app.post("/process-email")
async def process_email(request: Request):
    """
    Process an email through the agent.
    Triggers HITL if needed.
    """
    body = await request.json()
    
    workflow_id = str(uuid.uuid4())[:8]
    
    # ✅ Initialize state with empty lists (not None)
    email_data = {
        "email_id": workflow_id,
        "email_from": body.get("email_from", ""),
        "email_to": body.get("email_to", "you@company.com"),  # ✅ Add email_to
        "email_subject": body.get("email_subject", ""),
        "email_body": body.get("email_body", ""),
        "messages": [],
        "user_preferences": {},
        "workflow_id": workflow_id
    }
    
    print(f"\n📧 Processing email: {email_data['email_subject']}")
    
    # Notify UI that processing started
    await broadcast_message({
        "type": "processing_started",
        "workflow_id": workflow_id,
        "email": {
            "from": email_data["email_from"],
            "subject": email_data["email_subject"]
        }
    })
    
    # Run agent in background
    asyncio.create_task(
        run_agent_workflow(workflow_id, email_data)
    )
    
    return {
        "status": "processing",
        "workflow_id": workflow_id
    }


async def run_agent_workflow(workflow_id: str, email_data: dict):
    """
    Run the agent workflow asynchronously.
    Handles HITL pause/resume and notify_human.
    """
    try:
        config = {
            "configurable": {
                "thread_id": workflow_id
            }
        }
        
        # Phase 1: Run until HITL checkpoint or triage decision
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: agent.invoke(email_data, config)
        )
        
        # Get triage decision
        triage_decision = result.get("triage_decision", "")
        triage_reasoning = result.get("triage_reasoning", "")
        
        print("\n🔍 DEBUG:")
        print(f"   triage_decision: {triage_decision}")
        print(f"   requires_approval: {result.get('requires_approval')}")
        
        # Notify triage result
        await broadcast_message({
            "type": "triage_complete",
            "workflow_id": workflow_id,
            "decision": triage_decision,
            "reasoning": triage_reasoning
        })
        
        # ✅ Handle notify_human - show notification with options
        if triage_decision == "notify_human":
            print(f"\n🔔 NOTIFY_HUMAN: Showing notification with options")
            
            # Create notification approval
            approval_data = {
                "workflow_id": workflow_id,
                "action_type": "notify_human",
                "recipient": email_data["email_from"],
                "subject": email_data["email_subject"],
                "body": email_data["email_body"],
                "draft_preview": f"📧 **Notification Email**\n\nFrom: {email_data['email_from']}\nSubject: {email_data['email_subject']}\n\n{email_data['email_body'][:500]}...",
                "timestamp": datetime.now().isoformat(),
                "notification_type": True  # ✅ Flag for UI to show respond/ignore
            }
            
            # Store and broadcast
            pending_approvals[workflow_id] = approval_data
            approval_events[workflow_id] = asyncio.Event()
            
            await broadcast_message({
                "type": "approval_required",
                "data": approval_data
            })
            
            print(f"   ⏸️  Waiting for human decision (respond or ignore)")
            
            # Wait for human decision
            try:
                await asyncio.wait_for(
                    approval_events[workflow_id].wait(),
                    timeout=600
                )
            except asyncio.TimeoutError:
                print(f"   ⏰ Timed out")
                await broadcast_message({
                    "type": "workflow_timeout",
                    "workflow_id": workflow_id
                })
                return
            
            # Get decision
            decision_data = approval_decisions.get(workflow_id, {})
            decision = decision_data.get("decision", "ignore")
            
            print(f"\n   👤 Human chose: {decision}")
            
            if decision == "ignore":
                # Update memory: Save that this type of email should be ignored
                print(f"   💾 Updating memory: User ignored this notification")
                
                # Notify completion
                await broadcast_message({
                    "type": "workflow_complete",
                    "workflow_id": workflow_id,
                    "decision": "ignored",
                    "execution_status": "complete"
                })
                
                # ✅ Save to memory that email was denied/ignored
                from src.nodes.memory import get_memory
                memory = get_memory()
                if memory:
                    memory.save_email_interaction(
                        email_id=workflow_id,
                        email_from=email_data["email_from"],
                        email_subject=email_data["email_subject"],
                        triage_decision="notify_human",
                        action_taken="none",
                        human_approved=False  # ✅ This is the deny!
                    )
                
                return
            
            elif decision == "respond":
                print(f"   ▶️  User wants to respond - creating draft...")
                
                # ✅ FIX: Instead of re-invoking the whole workflow,
                # manually call the react_agent node
                from src.nodes.react_agent import react_agent_node
                
                # Update state to indicate we're responding
                email_data_for_draft = {
                    **result,  # Keep existing state
                    "triage_decision": "respond",
                    "email_id": email_data["email_id"],
                    "email_from": email_data["email_from"],
                    "email_to": email_data.get("email_to", "you@company.com"),
                    "email_subject": email_data["email_subject"],
                    "email_body": email_data["email_body"],
                }
                
                try:
                    print(f"   🤖 Calling react_agent to generate draft...")
                    
                    # Call react_agent directly in executor
                    draft_result = await loop.run_in_executor(
                        None,
                        lambda: react_agent_node(email_data_for_draft)
                    )
                    
                    print(f"   ✅ Draft created")
                    print(f"   Draft has pending_action: {draft_result.get('pending_action') is not None}")
                    
                    # Update result with draft
                    result = {
                        **result,
                        **draft_result,
                        "requires_approval": True  # Force approval
                    }
                    
                except Exception as e:
                    print(f"   ❌ Error creating draft: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    await broadcast_message({
                        "type": "workflow_error",
                        "workflow_id": workflow_id,
                        "error": f"Failed to create draft: {str(e)}"
                    })
                    return
        
        # ✅ Handle respond - show draft for approval
        if result.get("requires_approval"):
            pending_action = result.get("pending_action", {})
            args = pending_action.get("args", {})
            
            # Get draft preview
            messages = result.get('messages', [])
            draft_preview = ""
            if messages and len(messages) > 0:
                msg = messages[0]
                if isinstance(msg, dict):
                    draft_preview = msg.get("content", "")
                else:
                    draft_preview = str(msg)
            
            approval_data = {
                "workflow_id": workflow_id,
                "action_type": pending_action.get("action_type", ""),
                "recipient": args.get("recipient", ""),
                "subject": args.get("subject", ""),
                "body": args.get("body", ""),
                "draft_preview": draft_preview,
                "timestamp": datetime.now().isoformat(),
                "notification_type": False  # ✅ Regular approval
            }
            
            # Store and broadcast
            pending_approvals[workflow_id] = approval_data
            approval_events[workflow_id] = asyncio.Event()
            
            await broadcast_message({
                "type": "approval_required",
                "data": approval_data
            })
            
            print(f"\n⏸️  Workflow {workflow_id} paused for approval")
            
            # Wait for human decision
            try:
                await asyncio.wait_for(
                    approval_events[workflow_id].wait(),
                    timeout=600
                )
            except asyncio.TimeoutError:
                print(f"⏰ Workflow {workflow_id} timed out")
                await broadcast_message({
                    "type": "workflow_timeout",
                    "workflow_id": workflow_id
                })
                return
            
            # Get decision
            decision_data = approval_decisions.get(workflow_id, {})
            decision = decision_data.get("decision", "deny")
            edited_content = decision_data.get("edited_content", "")
            
            print(f"\n▶️  Resuming workflow {workflow_id}")
            print(f"   Decision: {decision}")
            print(f"   🔍 DEBUG: About to check decision type...")
            sys.stdout.flush()
            
            # ✅ Handle deny - save to memory
            if decision == "deny":
                print(f"   🚫 User denied - saving to memory")
                sys.stdout.flush()
                
                from src.nodes.memory import get_memory
                memory = get_memory()
                if memory:
                    memory.save_email_interaction(
                        email_id=workflow_id,
                        email_from=email_data["email_from"],
                        email_subject=email_data["email_subject"],
                        triage_decision=result.get("triage_decision", "respond"),
                        action_taken="none",
                        human_approved=False  # ✅ Denied!
                    )
                
                await broadcast_message({
                    "type": "workflow_complete",
                    "workflow_id": workflow_id,
                    "decision": "denied",
                    "execution_status": "cancelled"
                })
                return
            
            print(f"   🔍 DEBUG: Passed deny check, continuing...")
            sys.stdout.flush()
            
            # ✅ FIX: Instead of re-invoking the graph, manually execute and update memory
            
            # Update state with decision
            updated_state = {
                **result,
                "human_decision": decision
            }
            
            print(f"   🔍 DEBUG: Updated state created")
            sys.stdout.flush()
            
            if decision == "edit" and edited_content:
                print(f"   ✏️  User edited - using edited content")
                sys.stdout.flush()
                updated_state["human_feedback"] = {
                    "body_content": edited_content
                }
                updated_state["human_decision"] = "edit"
                
                # Update the pending_action with edited content
                if updated_state.get("pending_action"):
                    updated_state["pending_action"]["args"]["body"] = edited_content
            
            print(f"   ⚙️  Executing action...")
            sys.stdout.flush()
            
            # Manually call execute_action_node and update_memory_node
            from src.nodes.execute import execute_action_node
            from src.nodes.memory import update_memory_node
            
            print(f"   🔍 DEBUG: Imported nodes, about to execute...")
            sys.stdout.flush()
            
            try:
                # Execute the action
                print(f"   🔍 DEBUG: Calling execute_action_node...")
                sys.stdout.flush()
                
                execution_result = await loop.run_in_executor(
                    None,
                    lambda: execute_action_node(updated_state)
                )
                
                print(f"   ✅ Action executed: {execution_result.get('execution_status')}")
                sys.stdout.flush()
                
                # Update memory
                print(f"   🔍 DEBUG: Calling update_memory_node...")
                sys.stdout.flush()
                
                memory_result = await loop.run_in_executor(
                    None,
                    lambda: update_memory_node(execution_result)
                )
                
                print(f"   💾 Memory updated")
                sys.stdout.flush()
                
                # Notify completion
                await broadcast_message({
                    "type": "workflow_complete",
                    "workflow_id": workflow_id,
                    "decision": decision,
                    "execution_status": execution_result.get("execution_status", ""),
                    "execution_result": execution_result.get("execution_result", "")
                })
                
            except Exception as e:
                print(f"   ❌ Error executing/updating: {e}")
                import traceback
                traceback.print_exc()
                
                await broadcast_message({
                    "type": "workflow_error",
                    "workflow_id": workflow_id,
                    "error": f"Execution failed: {str(e)}"
                })
            
        else:
            # No approval needed (auto-processed)
            await broadcast_message({
                "type": "workflow_complete",
                "workflow_id": workflow_id,
                "decision": "auto_approved",
                "execution_status": "complete"
            })
    
    except Exception as e:
        print(f"❌ Workflow error: {e}")
        import traceback
        traceback.print_exc()
        
        await broadcast_message({
            "type": "workflow_error",
            "workflow_id": workflow_id,
            "error": str(e)
        })


@app.get("/pending-approvals")
async def get_pending_approvals():
    """Get all pending approvals."""
    return {
        "count": len(pending_approvals),
        "approvals": list(pending_approvals.values())
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent_ready": agent is not None,
        "gmail_connected": gmail_service is not None,
        "calendar_connected": calendar_service is not None,
        "pending_approvals": len(pending_approvals),
        "connected_clients": len(websocket_connections)
    }


@app.get("/stats")
async def get_stats():
    """Get memory statistics including deny counts."""
    from src.nodes.memory import get_memory
    
    memory = get_memory()
    if not memory:
        return {"error": "Memory not initialized"}
    
    stats = memory.get_stats()
    
    # ✅ Calculate deny count
    cursor = memory.conn.execute("""
        SELECT COUNT(*) 
        FROM email_history 
        WHERE human_approved = 0 AND action_taken != 'none'
    """)
    deny_count = cursor.fetchone()[0]
    
    # Calculate approve count
    cursor = memory.conn.execute("""
        SELECT COUNT(*) 
        FROM email_history 
        WHERE human_approved = 1
    """)
    approve_count = cursor.fetchone()[0]
    
    return {
        **stats,
        "deny_count": deny_count,
        "approve_count": approve_count,
        "pending_count": len(pending_approvals)
    }