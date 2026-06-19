from dotenv import load_dotenv

from utils.prevChat import fetch_previous_chat, get_session, append_to_session
from utils.rag import get_rag_context
from utils.tool import (
    get_student_details,
    get_student_scores,
    get_student_attendance,
    get_exam_schedule,
    get_all_student_details,
)

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)

load_dotenv()

llm = ChatOpenAI(
    model="gpt-5.4-mini-2026-03-17",
    temperature=0.3,
)

tools = [
    get_student_details,
    get_student_scores,
    get_student_attendance,
    get_exam_schedule,
    get_all_student_details,
    get_rag_context,
]

llm_with_tools = llm.bind_tools(tools)

tool_map = {
    "get_student_details": get_student_details,
    "get_student_scores": get_student_scores,
    "get_student_attendance": get_student_attendance,
    "get_exam_schedule": get_exam_schedule,
    "get_all_student_details": get_all_student_details,
    "get_rag_context": get_rag_context,
}


def build_history_messages(history, max_messages=10):
    """Convert stored chat history into LangChain messages."""
    messages = []
    if not history:
        return messages

    for item in history[-max_messages:]:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

    return messages


def generate_response(student_id, message, type, session_key):

    # Long-term memory from previous sessions (Mem0)
    past_history = fetch_previous_chat(student_id)

    # Current session messages (in-memory)
    current_session = get_session(session_key)

    role_instruction = {
        "student": """
You are a helpful tutor.
Explain simply.
Encourage improvement.
""",
        "coach": """
You are a student success coach.
Give actionable academic guidance.
"""
    }.get(type, "Be helpful.")

    system_prompt = f"""
You are an educational AI assistant.

Current student:
student_id = {student_id}

IMPORTANT:

Assume every message is coming from this student whose student_id is {student_id}.

Only handle queries related to academics, attendance, and exams, else say it is out of my scope.

Use tools only when required.

KNOWLEDGE BASE RULES (rag context):
- Use get_rag_context tool if the user asks about:
  • learning portal
  • program information
  • policies
  • documentation
  • URLs
  • academy information
  • anything not found in student tools

TOOLS:

1. get_student_details
    - Purpose: Return the roster record for a student.
    - Input: student_id (string)
    - Output: dict of roster fields (e.g., student_id, name, program, cohort, manager_email)

2. get_student_scores
    - Purpose: Return exam score entries for a student.
    - Input: student_id (string)
    - Output: list of dicts with keys: subject, score, max_score, date.

3. get_student_attendance
    - Purpose: Return attendance records for a student.
    - Input: student_id (string)
    - Output: list of dicts with keys: attendance_pct, week_of, classes_attended, classes_scheduled.

4. get_exam_schedule
    - Purpose: Return upcoming exam entries for a student.
    - Input: student_id (string)
    - Output: list of dicts with keys: subject, exam_date, exam_type.

5. get_all_student_details
    - Purpose: Return a compact list of all students.
    - Input: None
    - Output: list of dicts with keys: id, name.

6. get_rag_context
    - Purpose: Retrieve knowledge base context from the RAG document.
    - Input: query (string), optionally k (int)
    - Output: formatted extracted content from the knowledge base.

RULES:

- Never invent attendance, scores, or exam dates.
- Convert tool output into natural language.
- Never show raw JSON.
- Use student's actual name.
- Use conversation history to understand follow-up messages.

ATTENTION CHECK:

After answering, flag if:
- attendance below 75%
- upcoming exam in less than 7 days
- low score

If nothing stands out, say performance looks stable.

ROLE:
{role_instruction}
"""

    messages = [SystemMessage(content=system_prompt)]

    # 1. Long-term memory from Mem0 (previous sessions)
    if past_history:
        messages.append(SystemMessage(content="Context from previous sessions:"))
        messages.extend(build_history_messages(past_history))

    # 2. Current session messages (full continuity within session)
    messages.extend(build_history_messages(current_session, max_messages=50))

    # 3. Current user message
    messages.append(HumanMessage(content=message))

    # First LLM pass
    ai_msg = llm_with_tools.invoke(messages)

    # If no tool call needed
    if not ai_msg.tool_calls:
        append_to_session(session_key, [
            {"role": "user", "content": message},
            {"role": "assistant", "content": ai_msg.content},
        ])
        return ai_msg.content

    messages.append(ai_msg)

    # Execute all tool calls
    student_tool_names = {
        "get_student_details",
        "get_student_scores",
        "get_student_attendance",
        "get_exam_schedule",
    }

    for tool_call in ai_msg.tool_calls:
        tool_name = tool_call["name"]
        args = tool_call.get("args", {})

        if tool_name in student_tool_names:
            args["student_id"] = student_id

        try:
            result = tool_map[tool_name].invoke(args)
        except Exception as e:
            result = f"Tool error: {str(e)}"

        messages.append(
            ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
            )
        )

    # Final LLM pass
    final = llm_with_tools.invoke(messages)
    response_text = final.content

    # Save to current session only (not Mem0 yet)
    append_to_session(session_key, [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response_text},
    ])

    return response_text