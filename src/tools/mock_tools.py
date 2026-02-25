from langchain.tools import tool
from datetime import datetime, timedelta

@tool
def read_calendar(date: str) -> str:
    """
    Check calendar for availability on a given date.
    
    Args:
        date: Date in format YYYY-MM-DD
        
    Returns:
        Available time slots
    """
    print(f"🗓️ TOOL: Checking calendar for {date}")
    
    # Mock data 
    return f"Available slots on {date}: 10:00 AM, 2:00 PM, 4:00 PM"

@tool
def search_past_emails(query: str, sender: str = None) -> str:
    """
    Search past email history for context.
    
    Args:
        query: Search terms
        sender: Optional - filter by sender email
        
    Returns:
        Summary of relevant past emails
    """
    print(f"📧 TOOL: Searching emails for '{query}' from {sender or 'anyone'}")
    
    # Mock data
    if sender and "colleague" in sender:
        return "Found 3 past emails about Q4 project with this colleague. Last meeting was 2 weeks ago."
    
    return "No relevant past emails found."

@tool
def draft_email_reply(recipient: str, context: str) -> str:
    """
    Draft an email reply based on context.
    
    Args:
        recipient: Email address of recipient
        context: Context about what to include in the email
        
    Returns:
        Drafted email content
    """
    print(f"✍️ TOOL: Drafting email to {recipient}")
    
    # This would normally use an LLM, but for now return mock
    return f"""Hi,

Thanks for reaching out about {context}.

I'd be happy to discuss this further. Let me know what works for you.

Best regards"""