import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from src.agents.state import EmailAgentState

load_dotenv()

model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

llm = ChatGoogleGenerativeAI(
    model=model_name,
    temperature=0,
    timeout=45,
    max_retries=2,
    convert_system_message_to_human=True
)

triage_template = """You are an expert email triage assistant.

{memory_context}

**YOUR CAPABILITIES:**
You have access to tools that can:
- Check calendar availability
- Draft professional email responses
- Schedule meetings
- Search past emails for context

**CLASSIFICATION RULES:**

Classify this email into exactly ONE category:

1. **ignore** - Use ONLY for:
   ✓ Generic newsletters from marketing (company updates, general news)
   ✓ Automated notifications with no action needed (package shipped, social media likes)
   ✓ Spam and promotional content
   ✓ FYI emails that are not urgent or important
   
   Examples:
   - "New company newsletter available" → ignore
   - "5 people liked your post" → ignore
   - "Your package has shipped" → ignore
   
   ❌ DO NOT ignore:
   - Important industry newsletters (new tech releases, important updates)
   - Notifications about code reviews or pull requests
   - Reminders with deadlines

2. **notify_human** - Use ONLY for:
   ✓ Critical system alerts or urgent issues (server down, security alerts)
   ✓ HR deadlines and mandatory submissions requiring human action
   ✓ Financial matters (subscription renewals, billing issues)
   ✓ Reminders about personal decisions already made (maintenance windows)
   ✓ Important industry updates that need human awareness (new AI models, tech releases)
   ✓ Code review notifications and GitHub activity (human should review on platform)
   
   Examples:
   - "Submit expense reports by Friday" → notify_human (human must do this)
   - "Database maintenance tonight" → notify_human (important to know)
   - "CPU utilization exceeds threshold" → notify_human (urgent issue)
   - "Subscription will renew" → notify_human (financial decision)
   - "New Model from OpenAI" → notify_human (important tech update)
   - "PR #42: Comment from developer" → notify_human (review on GitHub)
   
   ❌ DO NOT notify_human for:
   - Requests you can acknowledge by email (even if personal)
   - Invitations you can express interest in

3. **respond** - Use for:
   ✓ ANY request you can answer by drafting an email
   ✓ Meeting requests (check calendar and suggest times)
   ✓ Technical questions (draft helpful responses)
   ✓ Requests for reviews or feedback (acknowledge and commit)
   ✓ Invitations or opportunities (express interest or ask questions)
   ✓ Personal appointment reminders (acknowledge and confirm will schedule)
   ✓ Registration invitations (express interest in signing up)
   ✓ ANY email where acknowledging by email is helpful
   
   Examples:
   - "Can we schedule a meeting?" → respond (check calendar, suggest times)
   - "Could you review these docs?" → respond (acknowledge, commit to review)
   - "Question about API docs" → respond (draft helpful response)
   - "Conference invitation" → respond (express interest, ask questions)
   - "Sign up daughter for swimming class" → respond (express interest in registering)
   - "Annual checkup reminder" → respond (acknowledge, confirm will schedule)
   
   ✅ KEY INSIGHT: Drafting "I'll take care of this" or "I'm interested" is responding!
   Even if the human must make final decision, acknowledging by email helps.

**IMPORTANT GUIDELINES:**
- DEFAULT to "respond" if you can draft ANY helpful acknowledgment or reply
- Use "notify_human" for CRITICAL alerts, deadlines, or when email is just FYI
- Use "ignore" ONLY for generic spam and unimportant automated notifications
- Remember: Expressing interest ≠ Making final decision
- Being helpful by drafting acknowledgment emails is your job!
- If memory context shows a triage override or pattern, FOLLOW IT

**EMAIL TO CLASSIFY:**

From: {email_from}
To: {email_to}
Subject: {email_subject}
Body: {email_body}

**YOUR CLASSIFICATION:**

Think step by step:
1. Check memory context for triage override or strong patterns
2. Is this just spam/generic newsletter with no importance? → If YES, classify as "ignore"
3. Is this a critical alert, deadline, important FYI, or GitHub notification? → If YES, classify as "notify_human"
4. Can I help by drafting an acknowledgment, interest, or response? → If YES, classify as "respond"

Respond in this EXACT format:
DECISION: [ignore/notify_human/respond]
REASONING: [One sentence explaining why, referencing the guidelines above]"""

triage_prompt = PromptTemplate(
    template=triage_template,
    input_variables=["email_from", "email_to", "email_subject", "email_body", "memory_context"]
)

def triage_node(state: EmailAgentState) -> EmailAgentState:
    """
    Classify email with memory-aware prompt.
    
    Memory structure from load_memory_node:
    user_preferences = {
        "raw": {
            "preferences": {...},
            "sender_context": {...},
            "past_feedback": [...],
            "triage_corrections": [...]
        },
        "summary": "...",
        "sender_context": {...},
        "triage_corrections": [...]
    }
    """
    
    # ✅ CORRECT: Access memory from user_preferences
    user_prefs = state.get("user_preferences", {})
    sender_context = user_prefs.get("sender_context")
    triage_corrections = user_prefs.get("triage_corrections", [])
    memory_summary = user_prefs.get("summary", "No memory available")
    
    email_from = state.get("email_from", "")
    
    # ✅ CHECK FOR TRIAGE OVERRIDE (auto-apply without LLM)
    if sender_context and sender_context.get("triage_override"):
        override = sender_context["triage_override"]
        print(f"  ⚡ TRIAGE OVERRIDE from memory: {override}")
        print(f"     Sender: {email_from}")
        return {
            **state,
            "triage_decision": override,
            "triage_reasoning": f"Memory override: sender {email_from} is always classified as '{override}'"
        }
    
    # ✅ BUILD MEMORY CONTEXT for LLM prompt
    memory_context_parts = []
    
    # Add summary
    if memory_summary and memory_summary != "No memory available":
        memory_context_parts.append("📋 MEMORY CONTEXT:")
        memory_context_parts.append(memory_summary)
    
    # Build final context string
    if memory_context_parts:
        memory_context = "\n".join(memory_context_parts)
    else:
        memory_context = "MEMORY CONTEXT: No previous interactions with this sender."
    
    # ✅ FORMAT PROMPT with all required variables
    prompt_text = triage_prompt.format(
        email_from=email_from,
        email_to=state.get("email_to", "Karan@company.com"),
        email_subject=state.get("email_subject", ""),
        email_body=state.get("email_body", ""),
        memory_context=memory_context
    )
    
    print(f"\n🤔 TRIAGE: Classifying email '{state.get('email_subject')}' with model {model_name}...", flush=True)

    # Invoke LLM with error handling and fallback
    decision = None
    reasoning = None

    try:
        response = llm.invoke(prompt_text)
        content = extract_text_content(response.content)
        for line in content.strip().split('\n'):
            if "DECISION:" in line:
                decision = line.split(":", 1)[1].strip().lower()
            elif "REASONING:" in line:
                reasoning = line.split(":", 1)[1].strip()
    except Exception as e:
        print(f"❌ Error invoking LLM for triage: {e}", flush=True)
        import traceback
        traceback.print_exc()
        decision = "notify_human"
        reasoning = f"Defaulted to notify_human due to LLM error: {str(e)}"

    # Validate decision
    if decision not in ["ignore", "notify_human", "respond"]:
        print(f"⚠️ Invalid decision '{decision}', defaulting to respond", flush=True)
        decision = "respond"
        reasoning = "Failed to parse, defaulting to respond to be helpful"
    
    # Clean output
    print(f"📋 TRIAGE: {decision.upper()}", flush=True)
    
    # Show context usage
    if sender_context:
        print(f"   📝 Sender known: {sender_context.get('sender_name', 'Unknown')}")
        print(f"   📊 Past interactions: {sender_context.get('interaction_count', 0)}")
    
    if triage_corrections:
        print(f"   🔄 Past corrections: {len(triage_corrections)} learned")
    
    return {
        **state,
        "triage_decision": decision,
        "triage_reasoning": reasoning
    }

def extract_text_content(content):
    """Gemini sometimes returns content as a string, sometimes as a list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
        return "\n".join(parts)
    return str(content)