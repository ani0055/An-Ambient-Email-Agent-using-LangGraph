import sqlite3
from datetime import datetime
from typing import Optional, Dict, List
import difflib
import re


class AgentMemory:
    """
    Memory system for email agent with pattern learning from feedback.
    """
    
    def __init__(self, db_path="agent_memory.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
    
    def _create_tables(self):
        """Create all necessary tables."""
        cursor = self.conn.cursor()
        
        # User preferences (learned patterns)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preference_key TEXT UNIQUE NOT NULL,
                preference_value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Sender context
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sender_context (
                sender_email TEXT PRIMARY KEY,
                sender_name TEXT,
                relationship TEXT,
                preferred_tone TEXT,
                triage_override TEXT,
                interaction_count INTEGER DEFAULT 0,
                notes TEXT,
                last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Email interaction history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT NOT NULL,
                email_from TEXT NOT NULL,
                email_subject TEXT,
                triage_decision TEXT,
                action_taken TEXT,
                human_approved BOOLEAN,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Feedback from edits
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_id TEXT NOT NULL,
                email_from TEXT NOT NULL,
                email_subject TEXT,
                original_draft TEXT,
                edited_draft TEXT,
                feedback_note TEXT,
                action TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Triage corrections
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS triage_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_from TEXT NOT NULL,
                email_subject TEXT,
                original_decision TEXT,
                corrected_decision TEXT,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        self.conn.commit()
    
    # ===== PREFERENCE MANAGEMENT =====
    
    def save_preference(self, key: str, value: str, confidence: float = 0.5):
        """Save or update a user preference."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO user_preferences (preference_key, preference_value, confidence, last_updated)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(preference_key) DO UPDATE SET
                preference_value = excluded.preference_value,
                confidence = excluded.confidence,
                last_updated = CURRENT_TIMESTAMP
        """, (key, value, confidence))
        self.conn.commit()
    
    def get_preferences(self) -> Dict:
        """Get all user preferences as a dictionary."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT preference_key, preference_value, confidence FROM user_preferences")
        
        prefs = {}
        for row in cursor.fetchall():
            key = row['preference_key']
            value = row['preference_value']
            
            # Parse list values
            if value.startswith('[') and value.endswith(']'):
                try:
                    # Simple list parsing (comma-separated)
                    value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(',') if v.strip()]
                except:
                    pass
            
            prefs[key] = value
        
        return prefs
    
    # ===== SENDER CONTEXT =====
    
    def save_sender_context(
        self,
        sender_email: str,
        sender_name: str = None,
        relationship: str = None,
        preferred_tone: str = None,
        triage_override: str = None,
        notes: str = None
    ):
        """Save or update sender context."""
        cursor = self.conn.cursor()
        
        # Get existing context
        cursor.execute("SELECT * FROM sender_context WHERE sender_email = ?", (sender_email,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing
            updates = []
            params = []
            
            if sender_name:
                updates.append("sender_name = ?")
                params.append(sender_name)
            if relationship:
                updates.append("relationship = ?")
                params.append(relationship)
            if preferred_tone:
                updates.append("preferred_tone = ?")
                params.append(preferred_tone)
            if triage_override:
                updates.append("triage_override = ?")
                params.append(triage_override)
            if notes:
                # Append to existing notes
                existing_notes = existing['notes'] or ""
                new_notes = f"{existing_notes}\n{notes}" if existing_notes else notes
                updates.append("notes = ?")
                params.append(new_notes)
            
            updates.append("interaction_count = interaction_count + 1")
            updates.append("last_interaction = CURRENT_TIMESTAMP")
            
            params.append(sender_email)
            
            if updates:
                cursor.execute(
                    f"UPDATE sender_context SET {', '.join(updates)} WHERE sender_email = ?",
                    params
                )
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO sender_context 
                (sender_email, sender_name, relationship, preferred_tone, triage_override, notes, interaction_count)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (sender_email, sender_name, relationship, preferred_tone, triage_override, notes))
        
        self.conn.commit()
    
    def get_sender_context(self, sender_email: str) -> Optional[Dict]:
        """Get context for a specific sender."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM sender_context WHERE sender_email = ?", (sender_email,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    # ===== EMAIL HISTORY =====
    
    def save_email_interaction(
        self,
        email_id: str,
        email_from: str,
        email_subject: str,
        triage_decision: str,
        action_taken: str,
        human_approved: bool
    ):
        """Save email interaction to history."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO email_history 
            (email_id, email_from, email_subject, triage_decision, action_taken, human_approved)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (email_id, email_from, email_subject, triage_decision, action_taken, human_approved))
        self.conn.commit()
    
    def get_sender_history(self, sender_email: str, limit: int = 10) -> List[Dict]:
        """Get past interactions with a sender."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM email_history 
            WHERE email_from = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (sender_email, limit))
        
        return [dict(row) for row in cursor.fetchall()]
    
    # ===== FEEDBACK & PATTERN LEARNING =====
    
    def save_feedback(
        self,
        email_id: str,
        email_from: str,
        email_subject: str,
        original_draft: str,
        edited_draft: str,
        feedback_note: str = "",
        action: str = "edit"
    ):
        """
        Save feedback and extract patterns.
        This is the KEY method that learns from edits.
        """
        cursor = self.conn.cursor()
        
        # 1. Save raw feedback
        cursor.execute("""
            INSERT INTO feedback_history 
            (email_id, email_from, email_subject, original_draft, edited_draft, feedback_note, action)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (email_id, email_from, email_subject, original_draft, edited_draft, feedback_note, action))
        
        # 2. ✅ EXTRACT PATTERNS from the diff
        patterns = self._analyze_edit_patterns(original_draft, edited_draft)
        
        # 3. Update preferences based on patterns
        for pattern_type, pattern_value in patterns.items():
            if pattern_value:
                self._update_preference_from_pattern(pattern_type, pattern_value)
        
        self.conn.commit()
        
        print(f"   🧠 Learned {len(patterns)} patterns from edit")
        for ptype, pval in patterns.items():
            if pval:
                print(f"      • {ptype}: {pval}")
    
    def _analyze_edit_patterns(self, original: str, edited: str) -> Dict:
        """
        ✅ CORE LEARNING FUNCTION
        Analyze differences between original and edited drafts.
        Extract patterns like tone, length, word choices.
        """
        patterns = {}
        
        # === LENGTH ANALYSIS ===
        orig_words = len(original.split())
        edit_words = len(edited.split())
        length_ratio = edit_words / orig_words if orig_words > 0 else 1.0
        
        if length_ratio < 0.6:
            patterns['length'] = 'brief'
            patterns['tone'] = 'concise'
        elif length_ratio > 1.4:
            patterns['length'] = 'detailed'
        
        # === GREETING/SIGN-OFF REMOVAL ===
        greeting_patterns = [
            r'^(hi|hello|hey|dear)\s+',
            r'^good\s+(morning|afternoon|evening)',
            r'(hi|hello)\s+[a-z]+[,\s]'
        ]
        signoff_patterns = [
            r'(best\s+regards|best|regards|sincerely|thanks|thank\s+you)',
            r'cheers[,\s]*$',
            r'kind\s+regards',
            r'warm\s+regards'
        ]
        
        # More robust detection
        orig_has_greeting = any(re.search(p, original.lower(), re.MULTILINE | re.IGNORECASE) for p in greeting_patterns)
        edit_has_greeting = any(re.search(p, edited.lower(), re.MULTILINE | re.IGNORECASE) for p in greeting_patterns)
        
        orig_has_signoff = any(re.search(p, original.lower(), re.MULTILINE | re.IGNORECASE) for p in signoff_patterns)
        edit_has_signoff = any(re.search(p, edited.lower(), re.MULTILINE | re.IGNORECASE) for p in signoff_patterns)
        
        if orig_has_greeting and not edit_has_greeting:
            patterns['no_greetings'] = 'true'
            print(f"      📌 Pattern detected: User removed greeting")
        
        if orig_has_signoff and not edit_has_signoff:
            patterns['no_sign_offs'] = 'true'
            print(f"      📌 Pattern detected: User removed sign-off")
        
        # === WORD CHOICE ANALYSIS ===
        # Words removed
        orig_words_set = set(re.findall(r'\b\w+\b', original.lower()))
        edit_words_set = set(re.findall(r'\b\w+\b', edited.lower()))
        
        removed_words = orig_words_set - edit_words_set
        added_words = edit_words_set - orig_words_set
        
        # Filter out common words
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'from', 'by', 'as', 'is', 'was', 'are', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'i', 'you', 'we', 'they', 'it', 'this', 'that', 'these', 'those'}
        
        removed_meaningful = removed_words - common_words
        added_meaningful = added_words - common_words
        
        if removed_meaningful:
            patterns['avoid_words'] = list(removed_meaningful)[:10]
        
        if added_meaningful:
            patterns['prefer_words'] = list(added_meaningful)[:10]
        
        # === PHRASE ANALYSIS ===
        # Detect removed phrases (2-3 word sequences)
        orig_bigrams = self._extract_ngrams(original, n=2)
        edit_bigrams = self._extract_ngrams(edited, n=2)
        
        removed_phrases = set(orig_bigrams) - set(edit_bigrams)
        added_phrases = set(edit_bigrams) - set(orig_bigrams)
        
        if removed_phrases:
            patterns['avoid_phrases'] = list(removed_phrases)[:5]
        
        if added_phrases:
            patterns['prefer_phrases'] = list(added_phrases)[:5]
        
        # === FORMALITY ANALYSIS ===
        formal_indicators = ['kindly', 'please', 'appreciate', 'regarding', 'furthermore', 'however']
        casual_indicators = ['hey', 'yeah', 'cool', 'awesome', 'sure', 'got it', 'sounds good']
        
        orig_formality = sum(1 for word in formal_indicators if word in original.lower())
        edit_formality = sum(1 for word in formal_indicators if word in edited.lower())
        
        orig_casual = sum(1 for word in casual_indicators if word in original.lower())
        edit_casual = sum(1 for word in casual_indicators if word in edited.lower())
        
        if edit_casual > orig_casual:
            patterns['formality'] = 'casual'
        elif edit_formality > orig_formality:
            patterns['formality'] = 'formal'
        
        return patterns
    
    def _extract_ngrams(self, text: str, n: int = 2) -> List[str]:
        """Extract n-grams (word sequences) from text."""
        words = re.findall(r'\b\w+\b', text.lower())
        return [' '.join(words[i:i+n]) for i in range(len(words)-n+1)]
    
    def _update_preference_from_pattern(self, pattern_type: str, pattern_value):
        """Update preferences based on extracted pattern."""
        
        # Handle list-type preferences (cumulative learning)
        if pattern_type in ['avoid_words', 'prefer_words', 'avoid_phrases', 'prefer_phrases']:
            existing = self.get_preferences().get(pattern_type, [])
            
            if not isinstance(existing, list):
                existing = []
            
            if isinstance(pattern_value, list):
                # Merge and deduplicate
                updated = list(set(existing + pattern_value))
                self.save_preference(pattern_type, str(updated), confidence=0.8)
            else:
                if pattern_value not in existing:
                    existing.append(pattern_value)
                    self.save_preference(pattern_type, str(existing), confidence=0.8)
        
        # Handle boolean preferences
        elif pattern_type in ['no_greetings', 'no_sign_offs']:
            self.save_preference(pattern_type, 'true', confidence=0.9)
        
        # Handle single-value preferences
        else:
            # Increase confidence with each confirmation
            existing_prefs = self.get_preferences()
            old_value = existing_prefs.get(pattern_type)
            
            if old_value == pattern_value:
                # Same pattern seen again - increase confidence
                self.save_preference(pattern_type, pattern_value, confidence=0.95)
            else:
                # New pattern
                self.save_preference(pattern_type, pattern_value, confidence=0.7)
    
    def get_past_feedback(self, limit: int = 10) -> List[Dict]:
        """Get recent feedback history."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM feedback_history 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    # ===== TRIAGE CORRECTIONS =====
    
    def save_triage_correction(
        self,
        email_from: str,
        email_subject: str,
        original_decision: str,
        corrected_decision: str,
        reason: str = ""
    ):
        """Save a triage correction."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO triage_corrections 
            (email_from, email_subject, original_decision, corrected_decision, reason)
            VALUES (?, ?, ?, ?, ?)
        """, (email_from, email_subject, original_decision, corrected_decision, reason))
        self.conn.commit()
    
    def get_triage_corrections(self, email_from: str = None) -> List[Dict]:
        """Get triage corrections, optionally filtered by sender."""
        cursor = self.conn.cursor()
        
        if email_from:
            cursor.execute("""
                SELECT * FROM triage_corrections 
                WHERE email_from = ? 
                ORDER BY timestamp DESC
            """, (email_from,))
        else:
            cursor.execute("""
                SELECT * FROM triage_corrections 
                ORDER BY timestamp DESC 
                LIMIT 20
            """)
        
        return [dict(row) for row in cursor.fetchall()]
    
    # ===== CONTEXT RETRIEVAL =====
    
    def get_full_context(self, sender_email: str) -> Dict:
        """
        Get complete context for decision making.
        This is the main method called by memory nodes.
        """
        return {
            "preferences": self.get_preferences(),
            "sender_context": self.get_sender_context(sender_email),
            "sender_history": self.get_sender_history(sender_email),
            "past_feedback": self.get_past_feedback(),
            "triage_corrections": self.get_triage_corrections(sender_email)
        }
    
    def close(self):
        """Close database connection."""
        self.conn.close()