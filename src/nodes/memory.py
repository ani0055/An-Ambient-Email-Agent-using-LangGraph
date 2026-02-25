from src.agents.state import EmailAgentState
from src.memory.agent_memory import AgentMemory

# Global memory instance
_memory = None


def initialize_memory(db_path="agent_memory.db"):
    """Initialize the memory system."""
    global _memory
    _memory = AgentMemory(db_path)
    print("✅ Memory initialized")
    return _memory


def get_memory() -> AgentMemory:
    """Get the current memory instance."""
    return _memory


def load_memory_node(state: EmailAgentState) -> EmailAgentState:
    """
    Loads user preferences and context from database.
    This runs BEFORE triage so all decisions are memory-informed.
    
    ✅ UPDATED to use get_full_context() from new AgentMemory
    """
    email_from = state.get('email_from', 'unknown')
    print(f"\n🧠 LOAD MEMORY: Fetching context for {email_from}")
    
    if not _memory:
        print("   ⚠️  Memory not initialized")
        return {**state, "user_preferences": {}}
    
    # ✅ Get full context using new method
    context = _memory.get_full_context(sender_email=email_from)
    
    # Extract components
    preferences = context.get('preferences', {})
    sender_context = context.get('sender_context')
    past_feedback = context.get('past_feedback', [])
    triage_corrections = context.get('triage_corrections', [])
    
    # Build memory summary for agent use
    memory_summary = []
    
    # 1. Add general preferences
    if preferences:
        prefs_text = "\n".join([f"  - {k}: {v}" for k, v in list(preferences.items())[:5]])
        memory_summary.append(f"📋 User Preferences:\n{prefs_text}")
    
    # 2. Add sender context (most important for triage)
    if sender_context:
        sender_name = sender_context.get('sender_name', 'Unknown')
        relationship = sender_context.get('relationship', 'Unknown')
        preferred_tone = sender_context.get('preferred_tone', 'professional')
        interaction_count = sender_context.get('interaction_count', 0)
        notes = sender_context.get('notes', '')
        
        memory_summary.append(
            f"👤 Sender Context ({email_from}):\n"
            f"  - Name: {sender_name}\n"
            f"  - Relationship: {relationship}\n"
            f"  - Preferred tone: {preferred_tone}\n"
            f"  - Past interactions: {interaction_count}"
        )
        
        if notes:
            # Show last 2 notes
            note_lines = notes.strip().split('\n')
            recent_notes = note_lines[-2:] if len(note_lines) > 2 else note_lines
            memory_summary.append(f"  - Notes:\n    " + "\n    ".join(recent_notes))
    
    # 3. Add past feedback patterns
    if past_feedback:
        feedback_summary = []
        for fb in past_feedback[:3]:
            subject = fb.get('email_subject', 'N/A')
            feedback_note = fb.get('feedback_note', '')
            if feedback_note:
                feedback_summary.append(f"  - '{subject}': {feedback_note}")
        
        if feedback_summary:
            memory_summary.append(
                f"✏️ Past Corrections:\n" + "\n".join(feedback_summary)
            )
    
    # 4. Add triage corrections (most relevant for triage node)
    if triage_corrections:
        corrections_text = []
        for tc in triage_corrections[:3]:
            subject = tc.get('email_subject', 'N/A')
            original = tc.get('original_decision', '')
            corrected = tc.get('corrected_decision', '')
            corrections_text.append(
                f"  - '{subject}': {original} → {corrected}"
            )
        
        if corrections_text:
            memory_summary.append(
                f"🔄 Triage Corrections:\n" + "\n".join(corrections_text)
            )
    
    # Final memory string
    final_memory = "\n\n".join(memory_summary) if memory_summary else "No memory available yet"
    
    # Print summary
    print(f"  ✓ Loaded {len(preferences)} preferences")
    if preferences:
        # Show key learned patterns
        for key in ['tone', 'length', 'formality']:
            if key in preferences:
                print(f"    - {key}: {preferences[key]}")
        if preferences.get('avoid_words'):
            avoid_count = len(preferences['avoid_words']) if isinstance(preferences['avoid_words'], list) else 0
            print(f"    - avoid_words: {avoid_count} words")
        if preferences.get('prefer_words'):
            prefer_count = len(preferences['prefer_words']) if isinstance(preferences['prefer_words'], list) else 0
            print(f"    - prefer_words: {prefer_count} words")
    
    print(f"  ✓ Sender known: {sender_context is not None}")
    if sender_context:
        print(f"    - Name: {sender_context.get('sender_name', 'Unknown')}")
        print(f"    - Interactions: {sender_context.get('interaction_count', 0)}")
        if sender_context.get('triage_override'):
            print(f"    - ⚡ Triage override: {sender_context.get('triage_override')}")
    print(f"  ✓ Past feedback: {len(past_feedback)} records")
    print(f"  ✓ Triage corrections: {len(triage_corrections)} records")
    
    # ✅ Return structure that both triage and react_agent expect
    return {
        **state,
        "user_preferences": {
            "raw": context,                          # Full raw data (for react_agent)
            "summary": final_memory,                 # Formatted text for LLM
            "sender_context": sender_context,        # Direct access
            "triage_corrections": triage_corrections, # Direct access
            "preferences": preferences                # Direct access (for react_agent)
        }
    }


def update_memory_node(state: EmailAgentState) -> EmailAgentState:
    """
    Update memory after processing email.
    ✅ UPDATED to use new AgentMemory methods with pattern extraction
    """
    print("\n💾 UPDATE MEMORY: Saving interaction and feedback")
    
    if not _memory:
        print("   ⚠️  Memory not initialized")
        return {**state, "memory_saved": False}
    
    # 1. Always save email interaction to history
    pending = state.get("pending_action", {})
    human_decision = state.get("human_decision")
    
    _memory.save_email_interaction(
        email_id=state.get("email_id", "unknown"),
        email_from=state.get("email_from", ""),
        email_subject=state.get("email_subject", ""),
        triage_decision=state.get("triage_decision", ""),
        action_taken=pending.get("action_type", "none") if pending else "none",
        human_approved=human_decision == "approve"
    )
    print(f"  ✓ Email interaction saved")
    
    # 2. ✅ SAVE FEEDBACK WITH PATTERN EXTRACTION
    if human_decision == "edit" and state.get("human_feedback"):
        original_draft = ""
        edited_draft = ""
        feedback_note = ""
        
        # Get original from messages
        messages = state.get("messages", [])
        if messages and isinstance(messages[0], dict):
            original_draft = messages[0].get("content", "")
            # Extract just the body (remove To: and Subject: lines)
            if "\n\n" in original_draft:
                original_draft = original_draft.split("\n\n", 1)[1]
        
        # Get edited version from human_feedback
        feedback = state.get("human_feedback", {})
        if isinstance(feedback, dict):
            edited_draft = feedback.get("body", "") or feedback.get("body_content", "")
            feedback_note = feedback.get("note", "")
        elif isinstance(feedback, str):
            edited_draft = feedback
        
        if original_draft and edited_draft and original_draft != edited_draft:
            print(f"  🔍 Analyzing edit patterns...")
            
            # ✅ THIS IS THE KEY FIX - save_feedback now extracts patterns
            _memory.save_feedback(
                email_id=state.get("email_id", "unknown"),
                email_from=state.get("email_from", ""),
                email_subject=state.get("email_subject", ""),
                original_draft=original_draft,
                edited_draft=edited_draft,
                feedback_note=feedback_note,
                action="edit"
            )
            print("  ✓ Saved feedback with pattern extraction")
            
            # ✅ Update sender context with note
            _memory.save_sender_context(
                sender_email=state.get("email_from", ""),
                notes=f"User edited response: '{state.get('email_subject', 'N/A')}' - {feedback_note if feedback_note else 'no note'}"
            )
            print("  ✓ Updated sender context")
        else:
            print("  ⚠️  No valid edit to analyze (drafts are identical or missing)")
    
    # 3. Save triage corrections if applicable
    if state.get("triage_corrected"):
        original_decision = state.get("triage_decision", "")
        corrected_decision = state.get("corrected_triage", "")
        correction_reason = state.get("correction_reason", "")
        
        # ✅ Use new save_triage_correction method
        _memory.save_triage_correction(
            email_from=state.get("email_from", ""),
            email_subject=state.get("email_subject", ""),
            original_decision=original_decision,
            corrected_decision=corrected_decision,
            reason=correction_reason
        )
        print(f"  ✓ Saved triage correction: {original_decision} → {corrected_decision}")
        
        # Check if we should create triage override (after 3+ corrections)
        corrections = _memory.get_triage_corrections(email_from=state.get("email_from", ""))
        if len(corrections) >= 3:
            # Count most common correction
            corrected_decisions = [c.get('corrected_decision') for c in corrections]
            most_common = max(set(corrected_decisions), key=corrected_decisions.count)
            count = corrected_decisions.count(most_common)
            
            if count >= 3:
                # Auto-create triage override
                _memory.save_sender_context(
                    sender_email=state.get("email_from", ""),
                    triage_override=most_common,
                    notes=f"⚡ Auto-learned triage override from {count} corrections"
                )
                print(f"  ⚡ Created triage override: always '{most_common}' for {state.get('email_from', '')}")
    
    print("  ✓ Memory updated successfully")
    return {**state, "memory_saved": True}


def save_memory_node(state: EmailAgentState) -> EmailAgentState:
    """
    Alternative name for update_memory_node.
    Some codebases use 'save' instead of 'update'.
    """
    return update_memory_node(state)