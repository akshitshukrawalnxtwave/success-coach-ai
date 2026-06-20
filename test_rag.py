from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
import streamlit as st

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=["https://www.googleapis.com/auth/calendar"]
)

service = build(
    "calendar",
    "v3",
    credentials=creds
)

print(
    service.calendarList()
    .list()
    .execute()
)