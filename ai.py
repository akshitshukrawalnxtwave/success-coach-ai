from dotenv import load_dotenv

from agent.prevChat import fetch_previous_chat
from agent.tool import (
    get_student_details,
    get_student_scores,
    get_student_attendance,
    get_exam_schedule,
    get_all_student_details
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
    temperature=0.3,   # lower = less random
)

tools = [
    get_student_details,
    get_student_scores,
    get_student_attendance,
    get_exam_schedule,
    get_all_student_details,
]

llm_with_tools = llm.bind_tools(tools)

tool_map = {
    "get_student_details": get_student_details,
    "get_student_scores": get_student_scores,
    "get_student_attendance": get_student_attendance,
    "get_exam_schedule": get_exam_schedule,
    "get_all_student_details": get_all_student_details,
}


def build_history_messages(history):
    """
    Convert stored chat history into LangChain messages.

    Expected format:
    [
        {"role":"user","content":"Hi"},
        {"role":"assistant","content":"Hello"}
    ]
    """

    messages = []

    if not history:
        return messages

    for item in history:

        if isinstance(item, dict):

            role = item.get("role")
            content = item.get("content", "")

            if role == "user":
                messages.append(HumanMessage(content=content))

            elif role == "assistant":
                messages.append(AIMessage(content=content))

        elif isinstance(item, str):
            # fallback if old format
            messages.append(HumanMessage(content=item))

    return messages


def generate_response(student_id, message, type):

    history = fetch_previous_chat(student_id)

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

only handle queries related to academics, attendance, and exams, else say it is out of my scope.

Ask for clarification.

Use tools only when required.

TOOLS:

1. get_student_details
    - Purpose: Return the roster record for a student.
    - Input: `student_id` (string)
    - Output: dict of roster fields (e.g., `student_id`, `name`, ...)

2. get_student_scores
    - Purpose: Return exam score entries for a student.
    - Input: `student_id` (string)
    - Output: list of dicts with keys: `subject`, `score`, `max_score`, `date`.

3. get_student_attendance
    - Purpose: Return attendance records for a student.
    - Input: `student_id` (string)
    - Output: list of dicts with keys: `attendance_pct`, `week_of`, `classes_attended`, `classes_scheduled`.

4. get_exam_schedule
    - Purpose: Return upcoming exam entries for a student.
    - Input: `student_id` (string)
    - Output: list of dicts with keys: `subject`, `exam_date`, `exam_type`.

5. get_all_student_details
    - Purpose: Return a compact list of all students.
    - Input: None
    - Output: list of dicts with keys: `id`, `name`.
    - Note: `db.get_all_students()` expects no arguments; the tool wrapper should not require `student_id`.


RULES:

- Never invent attendance.
- Never invent scores.
- Never invent exam dates.
- Convert tool output into natural language.
- Never show raw JSON.
- Use student's actual name.


ATTENTION CHECK:

After answering:

Flag:
- attendance below 75%
- upcoming exam (< 7 days)
- low score

If nothing stands out:
say performance looks stable.


ROLE:
{role_instruction}
"""

    messages = [
        SystemMessage(content=system_prompt)
    ]

    # Add previous conversation properly
    messages.extend(
        build_history_messages(history)
    )

    # Current message only
    messages.append(
        HumanMessage(content=message)
    )

    # First pass
    ai_msg = llm_with_tools.invoke(messages)

    # If no tool needed
    if not ai_msg.tool_calls:
        return ai_msg.content

    messages.append(ai_msg)

    # Execute tools
    for tool_call in ai_msg.tool_calls:

        tool_name = tool_call["name"]
        args = tool_call.get("args", {})

        # Inject student id automatically
        args["student_id"] = student_id

        try:
            result = tool_map[
                tool_name
            ].invoke(args)

        except Exception as e:

            result = (
                f"Tool error: {str(e)}"
            )

        messages.append(
            ToolMessage(
                content=str(result),
                tool_call_id=tool_call["id"],
            )
        )

    # Final response
    final = llm.invoke(messages)

    return final.content