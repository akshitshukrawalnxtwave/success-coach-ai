"""Generate and store structured session summaries (M5) in Mem0."""

from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from constants import OPEN_AI_MODEL
from utils.prevChat import save_memory_entry

load_dotenv()

_llm = ChatOpenAI(model=OPEN_AI_MODEL, temperature=0.2)


def _format_conversation(messages: list) -> str:
    return "\n".join(
        f"{msg.get('role', 'unknown').upper()}: {msg.get('content', '')}"
        for msg in messages
    )


def generate_session_summary(student_id: str, messages: list) -> str | None:
    """
    Build a structured session summary from a completed chat session.
    Returns None when there is not enough conversation to summarize.
    """
    if not messages or len(messages) < 2:
        return None

    system_prompt = """You are an educational session summarizer for student success coaches.
Summarize the completed tutoring/coaching session in 4-6 concise bullet points covering:
- Main academic topics discussed
- Student's current struggles or wins
- Emotional tone or engagement level (if evident)
- Any concerns that may need coach follow-up
- Suggested follow-up for the next human coaching session

Be factual. Do not invent details not present in the conversation."""

    human_prompt = f"""Student ID: {student_id}

SESSION TRANSCRIPT:
{_format_conversation(messages)}

Write the session summary:"""

    try:
        response = _llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])
        summary = (response.content or "").strip()
        return summary or None
    except Exception as e:
        print(f"Session summary generation error: {e}")
        return None


def save_session_summary(student_id: str, messages: list) -> bool:
    """
    Generate a session summary and persist it to Mem0.
    Stored with memory_type='session_summary' so retrieval can filter strictly.

    The [SESSION_SUMMARY timestamp] prefix is kept for human readability
    (e.g. coaches viewing raw memory) but is no longer needed as a filter tag
    since _search_memories now filters by metadata.memory_type directly.
    """
    summary = generate_session_summary(student_id, messages)
    if not summary:
        return False

    timestamp = datetime.now().isoformat(timespec="seconds")
    memory_text = (
        f"[SESSION_SUMMARY {timestamp}]\n"
        f"Student: {student_id}\n"
        f"{summary}"
    )
    return save_memory_entry(
        student_id=student_id,
        content=memory_text,
        memory_type="session_summary",  # strict type — used for filtering on retrieval
    )