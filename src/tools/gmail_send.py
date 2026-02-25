from email.mime.text import MIMEText
import base64
from googleapiclient.errors import HttpError

_gmail_service = None

def initialize_gmail_send(gmail_service):
    """Initialize Gmail service for sending."""
    global _gmail_service
    _gmail_service = gmail_service


def send_email_via_gmail(recipient: str, subject: str, body: str) -> dict:
    """
    Actually send email via Gmail API.
    
    Args:
        recipient: Email address
        subject: Email subject
        body: Email body (plain text)
    
    Returns:
        dict with status and message_id
    """
    if not _gmail_service:
        raise Exception("Gmail service not initialized")
    
    try:
        # Create message
        message = MIMEText(body)
        message['to'] = recipient
        message['subject'] = subject
        
        # Encode
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # Send
        sent_message = _gmail_service.users().messages().send(
            userId='me',
            body={'raw': raw}
        ).execute()
        
        return {
            "status": "success",
            "message_id": sent_message['id'],
            "thread_id": sent_message.get('threadId')
        }
        
    except HttpError as error:
        return {
            "status": "error",
            "error": str(error)
        }