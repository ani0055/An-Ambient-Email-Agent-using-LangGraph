from email.mime.text import MIMEText
import base64
import pytz
from langchain.tools import tool
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError

# Global services
_gmail_service = None
_calendar_service = None


def initialize_tools(gmail_service, calendar_service):
    """
    Initialize tools with authenticated Google services.
    Both gmail and calendar services stored here.
    """
    global _gmail_service, _calendar_service
    _gmail_service = gmail_service
    _calendar_service = calendar_service
    print("✅ Tools initialized with Google services")


def parse_indian_date(date_str: str) -> datetime:
    """Parse date in DD-MM-YYYY format."""
    try:
        return datetime.strptime(date_str, "%d-%m-%Y")
    except ValueError:
        return datetime.strptime(date_str, "%Y-%m-%d")


@tool
def check_calendar(
    start_date: str,
    end_date: str,
    timezone: str = "Asia/Kolkata"
) -> str:
    """Check calendar for available time slots between two dates."""
    if not _calendar_service:
        return "Error: Calendar service not initialized."

    try:
        tz = pytz.timezone(timezone)

        start_datetime = parse_indian_date(start_date)
        start_datetime = start_datetime.replace(hour=9, minute=0, second=0)
        start_datetime = tz.localize(start_datetime)

        end_datetime = parse_indian_date(end_date)
        end_datetime = end_datetime.replace(hour=17, minute=0, second=0)
        end_datetime = tz.localize(end_datetime)

        body = {
            "timeMin": start_datetime.isoformat(),
            "timeMax": end_datetime.isoformat(),
            "timeZone": timezone,
            "items": [{"id": "primary"}]
        }

        freebusy = _calendar_service.freebusy().query(body=body).execute()
        busy_times = freebusy['calendars']['primary']['busy']

        print(f"   Found {len(busy_times)} busy periods")

        available_slots = []
        current_day = start_datetime

        while current_day.date() <= end_datetime.date():
            if current_day.weekday() >= 5:
                current_day += timedelta(days=1)
                continue

            day_slots = []
            current_time = current_day.replace(hour=9, minute=0)
            day_end = current_day.replace(hour=17, minute=0)

            while current_time < day_end:
                slot_end = current_time + timedelta(hours=1)
                is_free = True

                for busy in busy_times:
                    busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                    busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))

                    if not (slot_end <= busy_start or current_time >= busy_end):
                        is_free = False
                        break

                if is_free:
                    day_slots.append(
                        f"{current_time.strftime('%I:%M %p')} - {slot_end.strftime('%I:%M %p')}"
                    )

                current_time = slot_end

            if day_slots:
                day_name = current_day.strftime("%A %d-%m-%Y")
                available_slots.append(f"{day_name}: {', '.join(day_slots[:3])}")

            current_day += timedelta(days=1)

        if available_slots:
            print(f"   ✓ Found {len(available_slots)} available days")
            return "Available time slots:\n" + "\n".join(
                [f"  • {slot}" for slot in available_slots]
            )
        else:
            return "No available slots found in the specified range."

    except Exception as e:
        return f"Error checking calendar: {str(e)}"


@tool
def schedule_meeting(
    title: str,
    start_time: str,
    duration_minutes: int,
    attendees: str,
    description: str = "",
    timezone: str = "Asia/Kolkata"
) -> str:
    """Schedule a meeting on Google Calendar."""
    if not _calendar_service:
        return "Error: Calendar service not initialized."

    try:
        tz = pytz.timezone(timezone)
        start_dt = datetime.strptime(start_time, "%d-%m-%Y %H:%M")
        start_dt = tz.localize(start_dt)
        end_dt = start_dt + timedelta(minutes=duration_minutes)

        attendee_list = [
            {"email": email.strip()} for email in attendees.split(",")
        ]

        event = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': timezone,
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': timezone,
            },
            'attendees': attendee_list,
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 30},
                ],
            }
        }

        created_event = _calendar_service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        return f"""✅ Meeting scheduled!
Title: {title}
When: {start_dt.strftime('%A, %d-%m-%Y at %I:%M %p')}
Duration: {duration_minutes} minutes
Attendees: {', '.join([a['email'] for a in attendee_list])}
Link: {created_event.get('htmlLink', 'N/A')}"""

    except Exception as e:
        return f"Error scheduling meeting: {str(e)}"


@tool
def draft_email_reply(
    recipient: str,
    subject: str,
    body_content: str,
    original_subject: str = ""
) -> str:
    """
    Draft an email reply with professional formatting.
    Creates a draft only - does NOT send.
    """
    # Add "Re:" prefix if replying
    if original_subject and not subject.startswith("Re:"):
        if subject.lower() == original_subject.lower():
            subject = f"Re: {original_subject}"

    # Return ONLY the body content
    # Subject and To are handled separately
    return body_content.strip()


@tool
def send_email_reply(
    recipient: str,
    subject: str,
    body: str,
    draft_preview: str = ""
) -> str:
    """
    Send an email reply via Gmail API.
    DANGEROUS - requires HITL approval before execution.
    """
    if not _gmail_service:
        return "Error: Gmail service not initialized."

    try:
        print(f"📤 SENDING EMAIL")
        print(f"   To: {recipient}")
        print(f"   Subject: {subject}")

        # Create email message
        message = MIMEText(body, 'plain')
        message['to'] = recipient
        message['subject'] = subject

        # Encode to base64
        raw_message = base64.urlsafe_b64encode(
            message.as_bytes()
        ).decode('utf-8')

        # Send via Gmail API
        sent = _gmail_service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()

        print(f"   ✓ Email sent! Message ID: {sent['id']}")

        return f"""✅ Email sent successfully!

To: {recipient}
Subject: {subject}
Message ID: {sent['id']}

Email has been delivered to {recipient}."""

    except Exception as e:
        error_msg = str(e)
        print(f"   ✗ Failed to send: {error_msg}")
        return f"Error sending email: {error_msg}"


def get_google_tools():
    """Returns list of all Google tools"""
    return [
        check_calendar,
        schedule_meeting,
        draft_email_reply,
        send_email_reply
    ]