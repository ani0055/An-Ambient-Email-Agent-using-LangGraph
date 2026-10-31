# 🤖 Ambient Email Agent with LangGraph

An intelligent email assistant that monitors your Gmail inbox, analyzes incoming emails, generates contextual responses, and learns from your feedback over time. Built with LangGraph, FastAPI, and Google APIs.

## ✨ Features

### 🧠 Intelligent Email Processing
- **Automatic Triage**: Classifies emails as `ignore`, `notify_human`, or `respond`
- **Smart Drafting**: Generates contextual email responses using Gemini AI
- **Calendar Integration**: Checks availability and suggests meeting times
- **Human-in-the-Loop (HITL)**: Requires approval before sending emails

### 📚 Persistent Memory System
- **Learns from Edits**: Analyzes your modifications to understand preferences
- **Pattern Recognition**: Detects greeting removal, sign-off preferences, tone, and word choices
- **Sender Context**: Remembers relationship and communication style per sender
- **Triage Corrections**: Learns when you override triage decisions

### 🎨 Real-Time Web Interface
- **Live Dashboard**: Monitor incoming emails and pending approvals
- **WebSocket Updates**: Real-time status updates and notifications
- **Interactive Approval**: Approve, edit, or deny draft emails in browser
- **Memory Insights**: View learned preferences and patterns

### ⚙️ Production Ready
- **Gmail Polling**: Automatically monitors inbox (configurable intervals)
- **Rate Limiting**: Handles API quotas gracefully
- **Error Recovery**: Robust error handling and retry logic
- **Async Processing**: Non-blocking workflow execution

## 🏗️ Architecture

<img width="1049" height="238" alt="overview-removebg-preview" src="https://github.com/user-attachments/assets/baa6e3ca-803e-4130-b97c-dade041bf188" />


## 🚀 Quick Start

### Prerequisites

- Python 3.9+
- Gmail account with API access
- Google Calendar access
- Gemini API key (or Claude API key)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/ambient-email-agent.git
cd ambient-email-agent
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up Google Cloud Project**

   a. Go to [Google Cloud Console](https://console.cloud.google.com/)
   
   b. Create a new project or select existing
   
   c. Enable APIs:
      - Gmail API
      - Google Calendar API
   
   d. Create OAuth 2.0 credentials:
      - Go to "Credentials" → "Create Credentials" → "OAuth client ID"
      - Application type: Desktop app
      - Download `credentials.json` and place in project root

4. **Set up API keys**

Create `.env` file:
```bash
GOOGLE_API_KEY=your_gemini_api_key_here
```

5. **Authenticate with Google**
```bash
python -c "from src.integrations.gmail_auth import authenticate_google_services; authenticate_google_services()"
```

This opens a browser for OAuth consent. Authorize the app.

6. **Run the agent**
```bash
python run_server.py
```

The server starts on `http://localhost:8000`

## 📖 Usage

### Starting the Agent

```bash
python run_server.py
```

You'll see:
```
🎯 EMAIL AGENT IS NOW LIVE!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 Monitoring Gmail inbox for new emails
🔄 Checking every 60 seconds
🌐 HITL Dashboard: http://localhost:8000
```

### Using the Web Interface

1. Open browser to `http://localhost:8000`
2. When a new email arrives, you'll see it appear in the dashboard
3. Review the AI-generated draft
4. Choose an action:
   - **Approve**: Send the draft as-is
   - **Edit**: Modify the draft before sending
   - **Deny**: Cancel and don't send

### Training the Memory System

The agent learns from your edits:

**Example 1: Remove Greetings**
```
AI Draft:
Hi John,
I'd be happy to help...
Best regards,

You Edit To:
I'd be happy to help...

✅ Agent learns: no_greetings = true
```

**Example 2: Make Concise**
```
AI Draft (50 words):
Thank you for reaching out. I would be delighted to assist...

You Edit To (20 words):
Happy to help. Available Tuesday 2pm?

✅ Agent learns: tone = concise, length = brief
```

After 3-5 edits, the agent will start generating drafts that match your style!

## 📁 Project Structure

```
ambient-email-agent/
├── src/
│   ├── agents/
│   │   ├── email_graph.py          # LangGraph workflow definition
│   │   └── state.py                # State schema
│   ├── nodes/
│   │   ├── memory.py               # Memory load/update nodes
│   │   ├── triage.py               # Email classification
│   │   ├── react_agent.py          # Draft generation with memory
│   │   ├── hitl.py                 # Human-in-the-loop checkpoint
│   │   └── execute.py              # Email sending execution
│   ├── tools/
│   │   └── google_tools.py         # Gmail & Calendar tools
│   ├── integrations/
│   │   ├── gmail_auth.py           # Google OAuth
│   │   └── gmail_fetch.py          # Email fetching utilities
│   └── memory/
│       └── agent_memory.py         # SQLite memory system with learning
├── ui/
│   ├── app.py                      # FastAPI server with WebSocket
│   └── templates/
│       └── index.html              # Web dashboard
├── gmail_poller.py                 # Gmail monitoring service
├── run_server.py                   # Production entry point
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

## ⚙️ Configuration

### Email Polling Interval

Edit `run_server.py`:
```python
poller = GmailPoller(
    gmail_service=gmail_service,
    poll_interval=20,      # Check every 20 seconds
    process_delay=15       # Wait 15s between emails (rate limiting)
)
```

### Triage Rules

Customize in `src/nodes/triage.py`:
- Ignore: Newsletters, spam, automated notifications
- Notify Human: Urgent alerts, deadlines, important FYIs
- Respond: Meeting requests, questions, actionable emails

### Memory Preferences

The agent automatically learns:
- `no_greetings` / `no_sign_offs`: Structural preferences
- `tone`: concise, casual, formal
- `length`: brief, normal, detailed
- `avoid_words` / `prefer_words`: Vocabulary preferences
- `avoid_phrases` / `prefer_phrases`: Phrase patterns

View learned preferences:
```bash
sqlite3 agent_memory.db "SELECT * FROM user_preferences;"
```

## 🔧 API Rate Limits

### Free Tier (Gemini)
- **Limit**: 5 requests/min
- **Solution**: Use rate-limited poller (included)
- **Config**: `process_delay=15` in gmail_poller.py

### Paid Tier
- **Limit**: 1000 requests/min
- **Config**: Set `process_delay=0` for instant processing

### Alternative: Claude API
Replace Gemini with Claude for higher limits:
```python
# In src/nodes/react_agent.py
from anthropic import Anthropic

client = Anthropic(api_key="your-key")
```

## 🐛 Troubleshooting

### "Insufficient Permissions" Error

**Solution**: Update Gmail scopes in `src/integrations/gmail_auth.py`:
```python
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',      
    'https://www.googleapis.com/auth/gmail.modify',    
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.events'
]
```

Then re-authenticate:
```bash
rm token.pickle
python -c "from src.integrations.gmail_auth import authenticate_google_services; authenticate_google_services()"
```

### "429 Rate Limit" Error

**Solution**: Use the rate-limited poller:
```bash
cp gmail_poller_RATE_LIMITED.py gmail_poller.py
```

Or upgrade to paid Gemini tier.

### Workflow Stuck at HITL

**Solution**: Use the fixed `run_server.py` that sends emails to FastAPI via HTTP instead of direct workflow invocation.

### Memory Not Learning

**Check**:
1. Memory initialized: Look for "✅ Memory initialized" in logs
2. Feedback saved: Look for "🧠 Learned X patterns from edit" after edits
3. Database exists: `ls agent_memory.db`
4. Patterns loaded: Check logs for "✓ Loaded X preferences"

## 📊 Monitoring

### Health Check
```bash
curl http://localhost:8000/health
```

### Pending Approvals
```bash
curl http://localhost:8000/pending-approvals
```

### Polling Status
```bash
curl http://localhost:8000/polling-status
```

### View Memory Database
```bash
sqlite3 agent_memory.db

.tables  # List all tables
SELECT * FROM user_preferences;
SELECT * FROM sender_context;
SELECT * FROM feedback_history;
```

## 🎯 Features Roadmap

- [ ] Multi-language support
- [ ] Slack integration
- [ ] Calendar event creation from emails
- [ ] Attachment handling
- [ ] Email threading and context
- [ ] Analytics dashboard
- [ ] Mobile app
- [ ] Voice command integration

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent orchestration framework
- [FastAPI](https://fastapi.tiangolo.com/) - Web framework
- [Google APIs](https://developers.google.com/) - Gmail and Calendar integration
- [Gemini AI](https://ai.google.dev/) - Language model

## 📧 Contact

Your Name – Animesh Gawhale

Project Link: https://github.com/ani0055/An-Ambient-Email-Agent-using-LangGraph.git
---

⭐ If you find this project helpful, please consider giving it a star!
