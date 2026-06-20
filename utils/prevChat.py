"""Session and memory management for student success coach."""

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
    return _search_memories(student_id, "previous conversation", limit=10)


def _search_memories(
    student_id: str,
    query: str,
    limit: int = 10,
    memory_type: str = None,
) -> list:
    """
    Search Mem0 for memories belonging to this student.
    Optionally filter by memory_type metadata (e.g. 'fact', 'session_summary').

    NOTE: Mem0's filter syntax may vary by SDK version. If the metadata filter
    key below does not work, check https://docs.mem0.ai for your version's syntax.
    Common variants:
        {"metadata.memory_type": memory_type}
        {"metadata__memory_type": memory_type}
        {"AND": [{"user_id": student_id}, {"metadata.memory_type": memory_type}]}
    """
    try:
        filters = {"user_id": student_id}
        if memory_type:
            filters["metadata.memory_type"] = memory_type

        results = client.search(
            query=query,
            filters=filters,
            limit=limit,
        )

        items = results.get("results", results)
        return [
            {
                "role": item.get("metadata", {}).get("role", "user"),
                "content": item.get("memory", ""),
            }
            for item in items
        ]

    except Exception as e:
        print(f"Mem0 fetch error: {e}")
        return []


def fetch_session_summaries(student_id: str) -> list:
    """
    Fetch stored session summaries for a student from Mem0.
    Filtered strictly by memory_type='session_summary' — no string-tag fallback needed.
    """
    return _search_memories(
        student_id,
        query="session summary coaching topics concerns follow-up",
        limit=8,
        memory_type="session_summary",
    )


def fetch_factual_memories(student_id: str) -> list:
    """
    Fetch factual academic memories for a student from Mem0.
    Filtered strictly by memory_type='fact'.
    """
    return _search_memories(
        student_id,
        query="academic performance attendance scores exams concerns progress",
        limit=10,
        memory_type="fact",
    )


def save_memory_entry(
    student_id: str,
    content: str,
    memory_type: str = "fact",
) -> bool:
    """Persist a single memory entry to Mem0 with memory_type in metadata."""
    try:
        client.add(
            messages=[{"role": "assistant", "content": content}],
            user_id=student_id,
            metadata={"memory_type": memory_type},
        )
        return True
    except TypeError:
        # Older Mem0 SDK may not accept metadata kwarg — save without it
        try:
            client.add(
                messages=[{"role": "assistant", "content": content}],
                user_id=student_id,
            )
            return True
        except Exception as e:
            print(f"Mem0 save error (no metadata): {e}")
            return False
    except Exception as e:
        print(f"Mem0 save error: {e}")
        return False


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
        client.add(
            messages=session,
            user_id=student_id,
        )
        print(f"Session saved to Mem0 Cloud for student {student_id}")
    except Exception as e:
        print(f"Mem0 save error: {e}")

    try:
        from utils.sessionSummary import save_session_summary
        save_session_summary(student_id, session)
    except Exception as e:
        print(f"Session summary save error: {e}")

    # Clear session from memory regardless
    _sessions.pop(session_key, None)