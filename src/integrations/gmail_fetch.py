import base64
from email.mime.text import MIMEText
from typing import List, Dict
import re

def get_recent_emails(service, max_results=10, query=""):
    """
    Fetch recent emails from Gmail.
    
    Args:
        service: Authenticated Gmail service
        max_results: Number of emails to fetch
        query: Gmail search query (e.g., "is:unread", "from:someone@example.com")
    
    Returns:
        List of email dictionaries
    """
    print(f"\n📧 Fetching {max_results} emails...")
    if query:
        print(f"   Query: {query}")
    
    try:
        # Get list of messages
        results = service.users().messages().list(
            userId='me',
            maxResults=max_results,
            q=query
        ).execute()
        
        messages = results.get('messages', [])
        
        if not messages:
            print("   No messages found.")
            return []
        
        print(f"   Found {len(messages)} messages. Fetching details...")
        
        # Fetch full details for each message
        emails = []
        for i, msg in enumerate(messages, 1):
            print(f"   [{i}/{len(messages)}] Fetching message {msg['id'][:8]}...")
            
            email_data = get_email_details(service, msg['id'])
            emails.append(email_data)
        
        print(f"✅ Successfully fetched {len(emails)} emails\n")
        return emails
        
    except Exception as e:
        print(f"❌ Error fetching emails: {e}")
        return []


def get_email_details(service, msg_id):
    """
    Get full details of a specific email.
    
    Args:
        service: Authenticated Gmail service
        msg_id: Gmail message ID
    
    Returns:
        Dictionary with email details
    """
    try:
        # Get the message
        message = service.users().messages().get(
            userId='me',
            id=msg_id,
            format='full'
        ).execute()
        
        # Extract headers
        headers = message['payload']['headers']
        
        subject = ""
        sender = ""
        date = ""
        
        for header in headers:
            name = header['name']
            value = header['value']
            
            if name.lower() == 'subject':
                subject = value
            elif name.lower() == 'from':
                sender = value
            elif name.lower() == 'date':
                date = value
        
        # Extract body
        body = extract_body(message['payload'])
        
        # Clean sender email (extract just email from "Name <email@domain.com>")
        email_match = re.search(r'<(.+?)>', sender)
        if email_match:
            sender_email = email_match.group(1)
        else:
            sender_email = sender
        
        return {
            'id': msg_id,
            'from': sender_email,
            'from_full': sender,  # Keep full name + email
            'subject': subject,
            'body': body[:500],  # Limit body length for processing
            'date': date,
            'snippet': message.get('snippet', '')
        }
        
    except Exception as e:
        print(f"   ⚠️  Error fetching message {msg_id}: {e}")
        return None


def extract_body(payload):
    """
    Extract email body from Gmail payload.
    Handles plain text and HTML emails.
    """
    body = ""
    
    if 'parts' in payload:
        # Multi-part message (text + HTML)
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain':
                if 'data' in part['body']:
                    body = base64.urlsafe_b64decode(
                        part['body']['data']
                    ).decode('utf-8')
                    break
        
        # If no plain text, try HTML
        if not body:
            for part in payload['parts']:
                if part['mimeType'] == 'text/html':
                    if 'data' in part['body']:
                        html = base64.urlsafe_b64decode(
                            part['body']['data']
                        ).decode('utf-8')
                        # Simple HTML strip (for demo - use BeautifulSoup for production)
                        body = re.sub('<[^<]+?>', '', html)
                        break
    else:
        # Simple message
        if 'body' in payload and 'data' in payload['body']:
            body = base64.urlsafe_b64decode(
                payload['body']['data']
            ).decode('utf-8')
    
    return body.strip()


def print_email_summary(email):
    """Pretty print email summary"""
    print(f"\n{'='*70}")
    print(f"From: {email['from_full']}")
    print(f"Subject: {email['subject']}")
    print(f"Date: {email['date']}")
    print(f"{'='*70}")
    print(f"Body preview:\n{email['body'][:200]}...")
    print(f"{'='*70}")