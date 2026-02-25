import os
import pickle
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Updated scopes - Gmail + Calendar
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',  # Read emails
    'https://www.googleapis.com/auth/gmail.send',      # Send emails (for later)
    'https://www.googleapis.com/auth/calendar.readonly',  # Read calendar
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar.events'     # Create events
]

def authenticate_google_services():
    """
    Authenticates with Google APIs (Gmail + Calendar).
    
    Returns:
        tuple: (gmail_service, calendar_service)
    """
    creds = None
    
    # Check if we have a saved token
    if os.path.exists('token.pickle'):
        print("📂 Loading saved credentials...")
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("🔐 Starting OAuth flow...")
            print("   A browser window will open for authentication.")
            print("   ⚠️  You'll need to grant Calendar permissions this time.")
            
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError(
                    "❌ credentials.json not found!\n"
                    "   Download it from Google Cloud Console."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', 
                SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # Save credentials
        print("💾 Saving credentials...")
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    
    print("✅ Authentication successful!")
    
    # Build services
    gmail_service = build('gmail', 'v1', credentials=creds)
    calendar_service = build('calendar', 'v3', credentials=creds)
    
    return gmail_service, calendar_service


def test_connection():
    """Test if Gmail and Calendar connections work"""
    try:
        gmail, calendar = authenticate_google_services()
        
        # Test Gmail
        profile = gmail.users().getProfile(userId='me').execute()
        print(f"\n✅ Gmail Connected!")
        print(f"   Email: {profile['emailAddress']}")
        
        # Test Calendar
        cal_list = calendar.calendarList().list().execute()
        print(f"\n✅ Calendar Connected!")
        print(f"   Found {len(cal_list.get('items', []))} calendars")
        for cal in cal_list.get('items', [])[:3]:
            print(f"      • {cal['summary']}")
        
        return gmail, calendar
        
    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        return None, None


if __name__ == "__main__":
    test_connection()