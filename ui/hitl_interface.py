from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
import asyncio
import json

app = FastAPI()

# Store pending approvals
pending_approvals = {}
approval_responses = {}

@app.get("/")
async def get_ui():
    """Serve the HITL approval interface."""
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>Email Agent - Approval Queue</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
        }
        .pending-item {
            border: 2px solid #ffa500;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            background: #fff8dc;
        }
        .email-preview {
            background: white;
            padding: 15px;
            border: 1px solid #ccc;
            margin: 10px 0;
            white-space: pre-wrap;
        }
        button {
            padding: 10px 20px;
            margin: 5px;
            font-size: 16px;
            cursor: pointer;
            border-radius: 5px;
        }
        .approve { background: #28a745; color: white; border: none; }
        .deny { background: #dc3545; color: white; border: none; }
        .edit { background: #007bff; color: white; border: none; }
        textarea {
            width: 100%;
            min-height: 150px;
            padding: 10px;
            margin: 10px 0;
        }
    </style>
</head>
<body>
    <h1>📧 Email Agent - Approval Queue</h1>
    <div id="pending-queue"></div>
    
    <script>
        const ws = new WebSocket('ws://localhost:8000/ws');
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            displayPendingApproval(data);
        };
        
        function displayPendingApproval(data) {
            const queue = document.getElementById('pending-queue');
            
            const item = document.createElement('div');
            item.className = 'pending-item';
            item.id = 'approval-' + data.workflow_id;
            
            item.innerHTML = `
                <h3>⚠️ Approval Required</h3>
                <p><strong>Action:</strong> ${data.action_type}</p>
                <p><strong>To:</strong> ${data.recipient}</p>
                <p><strong>Subject:</strong> ${data.subject}</p>
                
                <div class="email-preview">
                    ${data.preview}
                </div>
                
                <div id="edit-section-${data.workflow_id}" style="display:none;">
                    <h4>Edit Email:</h4>
                    <textarea id="edit-text-${data.workflow_id}">${data.body}</textarea>
                </div>
                
                <button class="approve" onclick="respond('${data.workflow_id}', 'approve')">
                    ✓ Approve & Send
                </button>
                <button class="deny" onclick="respond('${data.workflow_id}', 'deny')">
                    ✗ Deny
                </button>
                <button class="edit" onclick="toggleEdit('${data.workflow_id}')">
                    ✏️ Edit
                </button>
            `;
            
            queue.appendChild(item);
        }
        
        function toggleEdit(workflowId) {
            const editSection = document.getElementById('edit-section-' + workflowId);
            editSection.style.display = editSection.style.display === 'none' ? 'block' : 'none';
        }
        
        function respond(workflowId, decision) {
            let editedBody = null;
            
            if (decision === 'edit') {
                editedBody = document.getElementById('edit-text-' + workflowId).value;
                decision = 'approve';  // Edit means approve with changes
            }
            
            ws.send(JSON.stringify({
                workflow_id: workflowId,
                decision: decision,
                edited_body: editedBody
            }));
            
            // Remove from UI
            document.getElementById('approval-' + workflowId).remove();
        }
    </script>
</body>
</html>
    """)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time approval updates."""
    await websocket.accept()
    
    try:
        while True:
            # Wait for approval requests from agent
            data = await websocket.receive_text()
            message = json.loads(data)
            
            workflow_id = message.get("workflow_id")
            decision = message.get("decision")
            
            # Store response
            approval_responses[workflow_id] = {
                "decision": decision,
                "edited_body": message.get("edited_body")
            }
            
    except Exception as e:
        print(f"WebSocket error: {e}")


def request_approval(workflow_id: str, pending_action: dict) -> dict:
    """
    Request human approval via web UI.
    Called by the agent.
    """
    # This would be called from your HITL node
    # Return the human's decision
    pass


if __name__ == "__main__":
    print("🚀 Starting HITL Web Interface on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)