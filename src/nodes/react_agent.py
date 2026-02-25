from langchain_google_genai import ChatGoogleGenerativeAI
from src.agents.state import EmailAgentState
from src.tools.google_tools import get_google_tools
from datetime import datetime, timedelta
from langchain_core.messages import SystemMessage, HumanMessage
import json

# Use lower temperature for more consistent rule-following
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.1,
    convert_system_message_to_human=True
)

def extract_few_shot_examples(past_feedback, max_examples=2):
    """Create a few-shot string from past feedback showing before/after edits."""
    if not past_feedback:
        return ""
    
    examples = []
    for fb in past_feedback[:max_examples]:
        original = fb.get('original_draft', '').strip()
        edited = fb.get('edited_draft', '').strip()
        if original and edited and original != edited:
            examples.append(
                f"User's original draft:\n{original}\n\n"
                f"User's edited version (this is what they prefer):\n{edited}"
            )
    if examples:
        return (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "📚 EXAMPLES FROM YOUR PAST EDITS – FOLLOW THIS STYLE EXACTLY:\n"
            f"{chr(10).join(examples)}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
    return ""

def react_agent_node(state: EmailAgentState) -> EmailAgentState:
    """
    ReAct agent that creates actions requiring HITL approval.
    Now with ultra‑strong memory enforcement via few‑shot examples and explicit rules.
    """
    print(f"\n🤖 REACT AGENT: Processing email from {state['email_from']}")

    email_body = state['email_body'].lower()
    email_subject = state['email_subject'].lower()

    tools = get_google_tools()
    check_calendar_tool = tools[0]

    # Access memory (nested structure with fallback)
    user_prefs = state.get("user_preferences", {})
    raw_context = user_prefs.get("raw", {})
    preferences = raw_context.get("preferences", {})
    sender_context = raw_context.get("sender_context")
    past_feedback = raw_context.get("past_feedback", [])
    
    # Backwards compatibility
    if not preferences:
        preferences = user_prefs.get("preferences", {})
    if not sender_context:
        sender_context = user_prefs.get("sender_context")
    if not past_feedback:
        past_feedback = user_prefs.get("past_feedback", [])

    # Detect meeting request
    meeting_keywords = ['meet', 'schedule', 'call', 'sync', 'catch up', 'discuss', 'appointment', 'checkup']
    is_meeting_request = any(
        keyword in email_body or keyword in email_subject
        for keyword in meeting_keywords
    )

    calendar_info = ""

    # Check calendar if needed
    if is_meeting_request:
        start_date, end_date = extract_date_range(state['email_body'])
        try:
            calendar_result = check_calendar_tool.invoke({
                "start_date": start_date,
                "end_date": end_date,
                "timezone": "Asia/Kolkata"
            })
            calendar_info = calendar_result
            print("   ✓ Calendar checked")
        except Exception as e:
            calendar_info = ""

    # ------------------------------------------------------------------
    # Build ultra‑strong enforcement rules from memory
    # ------------------------------------------------------------------
    
    # Detect greeting/signoff removal from past edits
    has_no_greeting_pattern = False
    has_no_signoff_pattern = False
    
    if past_feedback:
        for fb in past_feedback[:5]:
            original = fb.get('original_draft', '').lower()
            edited = fb.get('edited_draft', '').lower()
            
            greeting_words = ['hi ', 'hello', 'dear ', 'hey ']
            orig_has_greeting = any(g in original for g in greeting_words)
            edit_has_greeting = any(g in edited for g in greeting_words)
            if orig_has_greeting and not edit_has_greeting:
                has_no_greeting_pattern = True
            
            signoff_words = ['best', 'regards', 'sincerely', 'thanks', 'cheers']
            orig_has_signoff = any(s in original for s in signoff_words)
            edit_has_signoff = any(s in edited for s in signoff_words)
            if orig_has_signoff and not edit_has_signoff:
                has_no_signoff_pattern = True
    
    # Parse preferences
    no_greetings = preferences.get("no_greetings") == 'true' or has_no_greeting_pattern
    no_signoffs = preferences.get("no_sign_offs") == 'true' or has_no_signoff_pattern
    tone_pref = preferences.get("tone")
    length_pref = preferences.get("length")
    formality_pref = preferences.get("formality")
    
    # Parse word/phrase lists
    avoid_words = preferences.get("avoid_words", [])
    prefer_words = preferences.get("prefer_words", [])
    avoid_phrases = preferences.get("avoid_phrases", [])
    prefer_phrases = preferences.get("prefer_phrases", [])
    
    # Convert string lists to actual lists
    for key, val in [('avoid_words', avoid_words), ('prefer_words', prefer_words), 
                      ('avoid_phrases', avoid_phrases), ('prefer_phrases', prefer_phrases)]:
        if isinstance(val, str):
            parsed = [w.strip().strip('"').strip("'") for w in val.strip('[]').split(',') if w.strip()]
            if key == 'avoid_words':
                avoid_words = parsed
            elif key == 'prefer_words':
                prefer_words = parsed
            elif key == 'avoid_phrases':
                avoid_phrases = parsed
            elif key == 'prefer_phrases':
                prefer_phrases = parsed
    
    # Build a single, forceful instruction block
    rules_text = []
    mandatory_instructions = []

    if no_greetings:
        mandatory_instructions.append("- You MUST NOT include any greeting (Hi, Hello, Dear, Hey, Good morning). Start directly with the main content.")
        print("   🧠 ENFORCING: No greetings")
    if no_signoffs:
        mandatory_instructions.append("- You MUST NOT include any sign-off (Best regards, Thanks, Sincerely, Cheers). End abruptly after the last sentence.")
        print("   🧠 ENFORCING: No sign-offs")
    if tone_pref == "concise" or length_pref == "brief":
        mandatory_instructions.append("- You MUST be extremely concise: maximum 2–3 short sentences. No explanations or pleasantries.")
        print("   🧠 ENFORCING: Ultra-brief")
    if avoid_words and len(avoid_words) > 0:
        forbidden = ', '.join(avoid_words[:10])
        mandatory_instructions.append(f"- You MUST NOT use these words: {forbidden}.")
        print(f"   🧠 ENFORCING: Avoid {len(avoid_words)} words")
    if prefer_words and len(prefer_words) > 0:
        preferred = ', '.join(prefer_words[:5])
        mandatory_instructions.append(f"- Where appropriate, try to use these preferred words: {preferred}.")
    if avoid_phrases and len(avoid_phrases) > 0:
        forbidden_phrases = ', '.join(avoid_phrases[:3])
        mandatory_instructions.append(f"- You MUST NOT use these phrases: {forbidden_phrases}.")
    if prefer_phrases and len(prefer_phrases) > 0:
        preferred_phrases = ', '.join(prefer_phrases[:3])
        mandatory_instructions.append(f"- Where appropriate, try to use these preferred phrases: {preferred_phrases}.")
    
    # Style preferences
    if formality_pref == "formal":
        mandatory_instructions.append("- Use a formal tone (no slang, contractions allowed only if natural in formal context).")
    elif formality_pref == "casual":
        mandatory_instructions.append("- Use a casual, friendly tone.")
    
    # Build the final rule block
    if mandatory_instructions:
        rules_block = (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️  STRICT RULES – LEARNED FROM YOUR PAST INTERACTIONS ⚠️\n"
            "You MUST follow EVERY rule below. Your draft will be REJECTED if any rule is violated.\n"
            + "\n".join(mandatory_instructions) + "\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
    else:
        rules_block = ""

    # Few-shot examples from past feedback
    examples_block = extract_few_shot_examples(past_feedback)

    # ------------------------------------------------------------------
    # Build the final prompt
    # ------------------------------------------------------------------
    system_instruction = (
        "You are an email writing assistant that drafts replies exactly as the user wants. "
        "Your goal is to produce a polished, ready‑to‑send email that perfectly matches all given rules and preferences. "
        "Do not add any commentary, explanations, or meta‑text – only output the email body."
    )

    main_prompt = f"""{system_instruction}

{'-'*60}
EMAIL TO REPLY TO:
From: {state['email_from']}
Subject: {state['email_subject']}
Body: {state['email_body']}
{'-'*60}

{ f"AVAILABLE TIME SLOTS:\n{calendar_info}" if calendar_info else "" }

{rules_block}

{examples_block}

Now write the email body according to ALL the rules above.
- Output ONLY the email body – no subject line, no "To:", no extra text.
- If a meeting is requested, propose 2–3 specific times from the available slots (if provided) or ask for preferences.
- Use DD‑MM‑YYYY format for dates.

Your draft:"""

    try:
        draft_response = llm.invoke(main_prompt)
        body_content = draft_response.content.strip()

        # Remove any accidental headers the LLM might still produce
        lines = body_content.split('\n')
        cleaned_lines = []
        for line in lines:
            if line.startswith("Subject:") or line.startswith("To:") or line.startswith("From:"):
                continue
            cleaned_lines.append(line)
        
        body_content = '\n'.join(cleaned_lines).strip()

        # ------------------------------------------------------------------
        # Post‑processing: if rules were violated, apply a quick fix
        # (this is a safety net; the prompt should already enforce them)
        # ------------------------------------------------------------------
        if no_greetings:
            # Remove first line if it's a greeting
            if lines and any(g in lines[0].lower() for g in ['hi ', 'hello', 'dear ', 'hey ', 'good morning']):
                lines = lines[1:]
                body_content = '\n'.join(lines).strip()
                print("   🔧 Forcefully removed greeting (post‑process)")
        if no_signoffs:
            # Remove last 1-2 lines if they're sign-offs
            while lines and any(s in lines[-1].lower() for s in ['best', 'regards', 'sincerely', 'thanks', 'cheers']):
                lines = lines[:-1]
                print("   🔧 Forcefully removed sign‑off (post‑process)")
            body_content = '\n'.join(lines).strip()

        print(f"   ✓ Draft created with {len(mandatory_instructions)} enforced rules")

    except Exception as e:
        body_content = "Available for meeting. Please confirm time."
        print(f"   ✗ Error creating draft: {e}")

    # Build formatted preview
    subject = f"Re: {state['email_subject']}" if not state['email_subject'].startswith('Re:') else state['email_subject']
    formatted_preview = f"""To: {state['email_from']}
Subject: {subject}

{body_content}"""

    # Create pending action (to be approved by HITL)
    pending_action = {
        "action_type": "send_email_reply",
        "args": {
            "recipient": state['email_from'],
            "subject": subject,
            "body": body_content,
            "draft_preview": formatted_preview
        }
    }

    print(f"   📤 Action queued: send_email_reply (requires approval)")

    messages = [
        {
            "role": "assistant",
            "content": formatted_preview,
            "metadata": {
                "is_meeting_request": is_meeting_request,
                "calendar_checked": bool(calendar_info),
                "body_only": body_content,
                "used_memory": bool(mandatory_instructions),
                "rules_applied": len(mandatory_instructions)
            }
        }
    ]

    return {
        **state,
        "messages": messages,
        "pending_action": pending_action
    }

def extract_date_range(email_body: str) -> tuple:
    """Extract date range from email or return defaults."""
    body_lower = email_body.lower()
    today = datetime.now()

    if 'tomorrow' in body_lower:
        start = today + timedelta(days=1)
        end = start + timedelta(days=1)
    elif 'next week' in body_lower:
        days_until_monday = (7 - today.weekday()) % 7
        if days_until_monday == 0:
            days_until_monday = 7
        start = today + timedelta(days=days_until_monday)
        end = start + timedelta(days=5)
    else:
        start = today + timedelta(days=1)
        end = start + timedelta(days=5)

    return start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y")