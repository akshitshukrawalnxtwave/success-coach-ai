import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# Google Calendar scope
SCOPES = [
    "https://www.googleapis.com/auth/calendar"
]

# Create credentials from Streamlit secrets
creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

# Build Calendar service
calendar_service = build(
    "calendar",
    "v3",
    credentials=creds
)

# Calendar email to insert events into
CALENDAR_ID = st.secrets["calendar_id"]

print("Calendar ID:", CALENDAR_ID)


def add_event(
    title,
    start_datetime,
    end_datetime,
    description=""
):
    """
    start_datetime/end_datetime:
    Example:
    2026-06-19T10:00:00
    """
    
    print("Calendar ID:", repr(CALENDAR_ID))

    event = {
        "summary": title,
        "description": description,
        "start": {
            "dateTime": start_datetime,
            "timeZone": "Asia/Kolkata"
        },
        "end": {
            "dateTime": end_datetime,
            "timeZone": "Asia/Kolkata"
        }
    }

    created = (
        calendar_service.events()
        .insert(
            calendarId=CALENDAR_ID,
            body=event
        )
        .execute()
    )

    return created