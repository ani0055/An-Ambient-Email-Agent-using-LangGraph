"""
Production Email Agent with Gmail Integration
Automatically processes incoming emails and triggers HITL approval
FIXED: Concurrent email processing - no more queue blocking!
"""

import asyncio
import threading
import time
import webbrowser

# Gmail integration
from src.integrations.gmail_auth import authenticate_google_services
from src.tools.google_tools import initialize_tools
from src.nodes.memory import initialize_memory

# Import UI app and its functions
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.app import app, run_agent_workflow

# Import Gmail poller
from gmail_poller import GmailPoller

# Global reference to the background asyncio loop
background_loop = None

def run_background_loop():
    """Create and run the background event loop."""
    global background_loop
    background_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(background_loop)
    background_loop.run_forever()

def process_incoming_email(email_data: dict):
    """
    Callback function for each incoming Gmail email.
    Creates a task to process the email concurrently (no blocking!).
    """
    print("\n" + "="*70)
    print("📬 NEW EMAIL RECEIVED")
    print("="*70)
    print(f"From: {email_data['from']}")
    print(f"Subject: {email_data['subject']}")
    print(f"ID: {email_data['id']}")
    print("="*70)
    
    # Prepare state for agent
    agent_input = {
        "email_id": email_data['id'],
        "email_from": email_data['from'],
        "email_to": email_data.get('to', 'you@company.com'),
        "email_subject": email_data['subject'],
        "email_body": email_data['body'],
        "user_preferences": {},
        "messages": [],
        "requires_approval": False,
        "human_decision": None,
        "pending_action": None,
        "workflow_id": email_data['id']
    }
    
    print(f"\n📥 Creating concurrent task for email processing...", flush=True)
    
    # ✅ FIX: Create a task instead of using a queue
    # This allows multiple emails to be processed concurrently
    future = asyncio.run_coroutine_threadsafe(
        run_agent_workflow(
            workflow_id=agent_input['workflow_id'],
            email_data=agent_input
        ),
        background_loop
    )

    def _task_done_callback(fut):
        try:
            exc = fut.exception()
            if exc:
                print(f"\n❌ Error in background email task for {agent_input['email_id']}: {exc}", flush=True)
                import traceback
                traceback.print_exception(type(exc), exc, exc.__traceback__)
        except Exception as e:
            print(f"Error checking future result: {e}", flush=True)

    future.add_done_callback(_task_done_callback)
    
    print(f"   ✅ Task created - email will process in background", flush=True)

def start_ui_server():
    """Start FastAPI UI server in background thread."""
    import uvicorn
    print("🌐 Starting HITL Web UI on http://localhost:8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

def open_browser():
    """Open the HITL dashboard in default browser."""
    time.sleep(2)
    webbrowser.open("http://localhost:8000")

def main():
    """Main entry point - starts everything."""
    global background_loop
    
    print("\n" + "="*70)
    print("🚀 EMAIL AGENT - PRODUCTION MODE (CONCURRENT)")
    print("="*70)
    
    # 1. Initialize memory
    print("\n1️⃣  Initializing memory database...")
    initialize_memory(db_path="agent_memory.db")
    print("   ✅ Memory initialized")
    
    # 2. Authenticate with Gmail
    print("\n2️⃣  Authenticating with Google...")
    try:
        gmail_service, calendar_service = authenticate_google_services()
        print("   ✅ Gmail authenticated")
        print("   ✅ Calendar authenticated")
    except Exception as e:
        print(f"   ❌ Authentication failed: {e}")
        return
    
    # 3. Initialize tools
    print("\n3️⃣  Initializing Google tools...")
    initialize_tools(gmail_service, calendar_service)
    print("   ✅ Tools initialized")
    
    # 4. Initialize agent in UI app
    print("\n4️⃣  Initializing LangGraph agent...")
    from src.agents.email_graph import create_email_agent
    from ui import app as ui_module
    
    ui_module.agent = create_email_agent()
    ui_module.gmail_service = gmail_service
    ui_module.calendar_service = calendar_service
    print("   ✅ Agent ready")
    
    # 5. Start UI server in background thread
    print("\n5️⃣  Starting web interface...")
    ui_thread = threading.Thread(target=start_ui_server, daemon=True)
    ui_thread.start()
    
    time.sleep(3)  # Give UI time to start
    print("   ✅ UI running at: http://localhost:8000")
    
    # Auto-open browser
    threading.Thread(target=open_browser, daemon=True).start()
    
    # 6. Start background event loop in its own thread
    print("\n6️⃣  Starting background event loop...")
    loop_thread = threading.Thread(target=run_background_loop, daemon=True)
    loop_thread.start()
    
    # Wait for loop to be ready
    while background_loop is None:
        time.sleep(0.1)
    
    print("   ✅ Background loop ready")
    print("   ℹ️  Emails will process CONCURRENTLY (no queue blocking)")

    # Share the background loop with the UI app
    from ui import app as ui_module
    ui_module.background_loop = background_loop
    print("   ✅ Background loop shared with UI")
    
    # 7. Start Gmail poller
    print("\n7️⃣  Starting Gmail poller...")
    poller = GmailPoller(gmail_service=gmail_service, poll_interval=20)
    
    print("\n" + "="*70)
    print("🎯 EMAIL AGENT IS NOW LIVE!")
    print("="*70)
    print("📧 Monitoring Gmail inbox for new emails")
    print("🔄 Checking every 20 seconds")
    print("🌐 HITL Dashboard: http://localhost:8000")
    print("⚡ Multiple emails will process concurrently")
    print("\nPress Ctrl+C to stop")
    print("="*70 + "\n")
    
    try:
        poller.start_polling(callback=process_incoming_email)
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("👋 Shutting down gracefully...")
        print("="*70)
        poller.stop()
        if background_loop and background_loop.is_running():
            background_loop.call_soon_threadsafe(background_loop.stop)
        loop_thread.join(timeout=2)
        print("✅ Shutdown complete. Goodbye!")

if __name__ == "__main__":
    main()