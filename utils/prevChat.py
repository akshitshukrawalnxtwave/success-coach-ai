import os
from mem0 import MemoryClient
from dotenv import load_dotenv

load_dotenv()

client = MemoryClient(api_key=os.getenv("SUCCESS_COACH_MEM0_API_KEY"))

# In-memory session store: { session_key: [ {role, content}, ... ] }
_sessions = {}


def get_session(session_key: str) -> list:
    """Get current in-memory session messages."""
    return _sessions.get(session_key, [])


def append_to_session(session_key: str, exchanges: list):
    """Append new exchanges to the current in-memory session."""
    if session_key not in _sessions:
        _sessions[session_key] = []
    _sessions[session_key].extend(exchanges)


def fetch_previous_chat(student_id: str) -> list:
    """Fetch long-term memory from Mem0 Cloud for this student."""
    try:
        results = client.search(
            query="previous conversation",
            filters={
                "user_id": student_id
            },
            limit=10
        )

        messages = []

        # Mem0 may return {"results": [...]} depending on SDK version
        items = results.get("results", results)

        for item in items:
            role = item.get("metadata", {}).get("role", "user")

            messages.append({
                "role": role,
                "content": item.get("memory", "")
            })

        return messages

    except Exception as e:
        print(f"Mem0 fetch error: {e}")
        return []

def end_session(session_key: str, student_id: str):
    """
    Called when user clicks End Session.
    Saves entire current session to Mem0 Cloud and clears in-memory session.
    """
    session = _sessions.get(session_key, [])
    if not session:
        print(f"No session found for {session_key}")
        return

    try:
        # Mem0 Cloud accepts a list of messages in one call
        client.add(
            messages=session,   # [ {role, content}, ... ]
            user_id=student_id
        )
        print(f"Session saved to Mem0 Cloud for student {student_id}")
    except Exception as e:
        print(f"Mem0 save error: {e}")

    # Clear session from memory regardless
    _sessions.pop(session_key, None)