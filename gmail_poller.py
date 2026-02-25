"""
Gmail Poller
Continuously monitors Gmail inbox for new emails
"""

import base64
import time
from email.parser import BytesParser
from email.policy import default
from typing import Callable, Optional, List, Dict
import re


class GmailPoller:
    """
    Continuously polls Gmail for new unread emails.
    Processes each email through a callback function.
    """
    
    def __init__(self, gmail_service, poll_interval: int = 60):
        """
        Initialize Gmail poller.
        
        Args:
            gmail_service: Authenticated Gmail API service
            poll_interval: Seconds between checks (default: 60)
        """
        self.gmail = gmail_service
        self.poll_interval = poll_interval
        self.processed_ids = set()
        self.running = False
    
    def fetch_unread_emails(self) -> List[Dict]:
        """
        Fetch unread emails from Gmail inbox.
        
        Returns:
            List of email dicts with id, from, to, subject, body
        """
        try:
            # Query Gmail for unread emails in inbox
            results = self.gmail.users().messages().list(
                userId='me',
                q='is:unread in:inbox',
                maxResults=10
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return []
            
            emails = []
            for msg in messages:
                # Skip if already processed this session
                if msg['id'] in self.processed_ids:
                    continue
                
                # Get full message
                try:
                    full_msg = self.gmail.users().messages().get(
                        userId='me',
                        id=msg['id'],
                        format='raw'
                    ).execute()
                    
                    # Parse email
                    email_data = self._parse_message(full_msg)
                    
                    if email_data:
                        emails.append(email_data)
                        self.processed_ids.add(msg['id'])
                        
                except Exception as e:
                    print(f"   ❌ Error fetching message {msg['id']}: {e}")
                    continue
            
            return emails
            
        except Exception as e:
            print(f"❌ Error fetching emails: {e}")
            return []
    
    def _parse_message(self, message: dict) -> Optional[Dict]:
        """
        Parse Gmail message into structured format.
        
        Args:
            message: Gmail API message object
            
        Returns:
            Dict with email fields or None if parsing fails
        """
        try:
            # Decode base64 raw message
            raw = base64.urlsafe_b64decode(message['raw'])
            
            # Parse with email library
            parsed = BytesParser(policy=default).parsebytes(raw)
            
            # Extract headers
            email_from = parsed.get('From', '')
            email_to = parsed.get('To', '')
            subject = parsed.get('Subject', '')
            
            # Clean up from field (extract just email if has name)
            # "John Doe <john@example.com>" → "john@example.com"
            from_match = re.search(r'<(.+?)>', email_from)
            if from_match:
                email_from_clean = from_match.group(1)
            else:
                email_from_clean = email_from.strip()
            
            # Extract body (prefer plain text)
            body = ""
            if parsed.is_multipart():
                for part in parsed.walk():
                    content_type = part.get_content_type()
                    if content_type == 'text/plain':
                        try:
                            body = part.get_content()
                            break
                        except:
                            pass
                    elif content_type == 'text/html' and not body:
                        # Fallback to HTML if no plain text
                        try:
                            html_body = part.get_content()
                            # Basic HTML stripping
                            body = re.sub('<[^<]+?>', '', html_body)
                        except:
                            pass
            else:
                try:
                    body = parsed.get_content()
                except:
                    body = "Could not extract email body"
            
            # Clean up body
            body = body.strip()
            
            return {
                "id": message['id'],
                "from": email_from_clean,
                "from_full": email_from,  # Keep full "Name <email>" format
                "to": email_to,
                "subject": subject,
                "body": body,
                "thread_id": message.get('threadId'),
                "labels": message.get('labelIds', [])
            }
            
        except Exception as e:
            print(f"❌ Error parsing message {message.get('id')}: {e}")
            return None
    
    def mark_as_read(self, email_id: str):
        """
        Mark email as read in Gmail.
        
        Args:
            email_id: Gmail message ID
        """
        try:
            self.gmail.users().messages().modify(
                userId='me',
                id=email_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            print(f"   ✅ Marked as read")
        except Exception as e:
            print(f"   ⚠️  Could not mark as read: {e}")
    
    def add_label(self, email_id: str, label: str):
        """
        Add a label to email.
        
        Args:
            email_id: Gmail message ID
            label: Label to add (e.g., 'PROCESSED')
        """
        try:
            self.gmail.users().messages().modify(
                userId='me',
                id=email_id,
                body={'addLabelIds': [label]}
            ).execute()
        except Exception as e:
            print(f"   ⚠️  Could not add label: {e}")
    
    def start_polling(self, callback: Callable[[Dict], None]):
        """
        Start continuous polling loop.
        
        Args:
            callback: Function to call for each email.
                     Should accept email_data dict as argument.
        """
        self.running = True
        
        print(f"\n{'='*70}")
        print(f"📧 GMAIL POLLER STARTED")
        print(f"{'='*70}")
        print(f"⏰ Checking every {self.poll_interval} seconds")
        print(f"📬 Monitoring inbox for unread emails")
        print(f"Press Ctrl+C to stop")
        print(f"{'='*70}\n")
        
        consecutive_errors = 0
        max_errors = 5
        
        while self.running:
            try:
                # Fetch new emails
                emails = self.fetch_unread_emails()
                
                if emails:
                    print(f"\n📬 Found {len(emails)} new email(s)")
                    
                    for email in emails:
                        print(f"\n{'─'*70}")
                        print(f"📧 New Email:")
                        print(f"   From: {email['from_full']}")
                        print(f"   Subject: {email['subject']}")
                        print(f"   ID: {email['id']}")
                        print(f"{'─'*70}")
                        
                        try:
                            # Call the callback function (triggers agent workflow)
                            callback(email)
                            
                            # Mark as read after successful processing
                            self.mark_as_read(email['id'])
                            
                            # Reset error counter on success
                            consecutive_errors = 0
                            
                        except Exception as e:
                            print(f"   ❌ Error in callback: {e}")
                            import traceback
                            traceback.print_exc()
                            consecutive_errors += 1
                else:
                    # No new emails - just print timestamp occasionally
                    current_time = time.strftime("%H:%M:%S")
                    print(f"[{current_time}] ✓ No new emails", end='\r')
                
                # Check if too many consecutive errors
                if consecutive_errors >= max_errors:
                    print(f"\n❌ Too many consecutive errors ({consecutive_errors})")
                    print(f"   Pausing for 5 minutes...")
                    time.sleep(300)  # Wait 5 minutes
                    consecutive_errors = 0
                
                # Wait before next check
                time.sleep(self.poll_interval)
                
            except KeyboardInterrupt:
                print("\n\n👋 Stopping poller...")
                self.running = False
                break
                
            except Exception as e:
                print(f"\n❌ Poller error: {e}")
                consecutive_errors += 1
                time.sleep(self.poll_interval)
    
    def stop(self):
        """Stop the polling loop."""
        self.running = False
        print("📧 Poller stopped")