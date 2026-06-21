from dotenv import load_dotenv
from datetime import datetime, timedelta

from constants import OPEN_AI_MODEL

from utils.prevChat import fetch_previous_chat, get_session, append_to_session
from utils.rag import get_rag_context
from utils.sheets import db
from utils.tool import (
    get_student_details,
    get_student_scores,
    get_student_attendance,
    get_exam_schedule,
    get_all_student_details,
)
from agents.generatePlan import add_event_to_calendar, generate_plan
from agents.preMeetingBrief import get_pre_meeting_brief

from langchain_openai import ChatOpenAI
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from langchain_core.tools import StructuredTool

load_dotenv()

llm = ChatOpenAI(
    model=OPEN_AI_MODEL,
    temperature=0.3,
)

# ============================================
# STUDENT TOOLS
# ============================================

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
    "get_student_details":    get_student_details,
    "get_student_scores":     get_student_scores,
    "get_student_attendance": get_student_attendance,
    "get_exam_schedule":      get_exam_schedule,
    "get_all_student_details": get_all_student_details,
    "get_rag_context":        get_rag_context,
}


def build_history_messages(history, max_messages=10):
    """Convert stored chat history into LangChain messages."""
    messages = []
    if not history:
        return messages

    for item in history[-max_messages:]:
        if isinstance(item, dict):
            role    = item.get("role")
            content = item.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

    return messages


# ============================================
# COACH HELPER FUNCTIONS
# ============================================

def get_student_history(student_id: str):
    """Fetch comprehensive history and context for a student"""
    student = db.get_student_details(student_id)
    if not student:
        return f"No student found with ID {student_id}"

    history    = fetch_previous_chat(student_id)
    scores     = db.get_student_scores(student_id)
    attendance = db.get_student_attendance(student_id)
    exams      = db.get_exams_schedule(student_id)

    result = f"""
STUDENT: {student.get('name')} (ID: {student_id})
Program: {student.get('program')} | Cohort: {student.get('cohort')}
Manager: {student.get('manager_email')}

RECENT INTERACTIONS:
{_format_history(history) if history else 'No previous interactions'}

CURRENT PERFORMANCE:
Latest Score:      {scores[-1]     if scores     else 'No data'}
Latest Attendance: {attendance[-1] if attendance else 'No data'}
Upcoming Exams:    {len(exams)} exams scheduled
"""
    return result


def get_action_plan(student_id: str):
    """Get recommended actions based on student's signal"""
    signals = db.get_signals()
    signal  = next((s for s in signals if s.get('student_id') == student_id), None)

    if not signal:
        return f"No active signal for student {student_id}"

    signal_type = signal.get('signal_type')
    actions = {
        "Academic": [
            "Schedule tutoring session",
            "Review exam strategy",
            "Check understanding of concepts",
            "Assign practice problems",
        ],
        "Attendance": [
            "Discuss barriers to attendance",
            "Set attendance goals",
            "Check for personal/health issues",
            "Recommend study groups",
        ],
        "Mental Health": [
            "Listen empathetically",
            "Connect to counseling services",
            "Discuss time management",
            "Encourage peer support",
        ],
        "Behavioral": [
            "Address concerns directly",
            "Discuss expectations",
            "Create improvement plan",
            "Schedule follow-up",
        ],
        "Other": [
            "Investigate further",
            "Schedule detailed discussion",
            "Document concerns",
        ],
    }

    plan  = f"ACTION PLAN — {signal_type} (Severity: {signal.get('severity')}, Urgency: {signal.get('urgency')})\n"
    plan += f"Reason: {signal.get('reason')}\n\nRECOMMENDED ACTIONS:\n"
    for i, action in enumerate(actions.get(signal_type, actions["Other"]), 1):
        plan += f"{i}. {action}\n"

    return plan


def _format_history(history):
    """Format chat history for readability"""
    if not history:
        return "None"
    recent = history[-2:]
    return "\n".join(
        [f"- {h.get('role', '').upper()}: {h.get('content', '')[:80]}..." for h in recent]
    )


# ============================================
# COACH TOOLS — registered for LLM binding
# ============================================

coach_tools = [
    StructuredTool.from_function(generate_plan),
    StructuredTool.from_function(get_student_history),
    StructuredTool.from_function(get_action_plan),
    StructuredTool.from_function(get_pre_meeting_brief),
    StructuredTool.from_function(add_event_to_calendar),
]

coach_tool_map = {
    "generate_plan":           generate_plan,
    "get_student_history":     get_student_history,
    "get_action_plan":         get_action_plan,
    "get_pre_meeting_brief":   get_pre_meeting_brief,
    "add_event_to_calendar":   add_event_to_calendar,
}


# ============================================
# COACH RESPONSE
# ============================================

def coach_response(message, session_key):
    """Coach assistant with access to planning and student history tools"""
    current_session = get_session(session_key)

    system_prompt = """
You are a student success coach assistant. Your job is to help the coach manage their day
efficiently and act on student signals.

TOOLS YOU HAVE:
1. generate_plan         — Builds today's prioritised coaching schedule, slots students 2–6 PM,
                           defers overflow to tomorrow, and auto-creates Google Calendar events.
2. get_student_history   — Returns full academic history, attendance, scores and past interactions
                           for a specific student. Requires student_id.
3. get_action_plan       — Returns a recommended action checklist for a student based on their
                           active signal type. Requires student_id.
4. get_pre_meeting_brief — Returns a focused pre-meeting brief for a student before a coaching
                           session. Covers current academic situation, changes since last session,
                           open concerns, and conversation starters. Requires student_id or name.
5. add_event_to_calendar — Manually adds a single coaching session to Google Calendar.
   Requires student_id, event_type, date (YYYY-MM-DD), slot (24hr HH:MM format, e.g. '15:00').
   Valid slots: '14:00', '15:00', '16:00', '17:00'.

WHEN TO CALL EACH TOOL:
- User says anything like "show my plan", "what's today", "generate plan", "who do I meet",
  "today's schedule", "start my day" → call generate_plan immediately, no further questions.
- User asks about a specific student's background, history, or performance → call get_student_history.
- User asks what to do with / for a student → call get_action_plan.
- User asks for a pre-meeting brief, prep, talking points, conversation starters, or what to
  discuss before meeting a student → call get_pre_meeting_brief with that student's id or name.
- User wants to manually book a session → call add_event_to_calendar.

RULES:
- Always call the appropriate tool; do not answer from memory.
- Be concise and data-driven in your responses.
- If generate_plan returns calendar event results, summarise them clearly.
- Never show raw dicts or JSON to the coach.
"""

    llm_coach           = ChatOpenAI(model=OPEN_AI_MODEL, temperature=0.3)
    coach_llm_with_tools = llm_coach.bind_tools(coach_tools)

    messages = [SystemMessage(content=system_prompt)]
    messages.extend(build_history_messages(current_session, max_messages=20))
    messages.append(HumanMessage(content=message))

    ai_msg = coach_llm_with_tools.invoke(messages)

    # No tool call needed — direct answer
    if not ai_msg.tool_calls:
        append_to_session(session_key, [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": ai_msg.content},
        ])
        return ai_msg.content

    messages.append(ai_msg)

    # Execute all tool calls
    for tool_call in ai_msg.tool_calls:
        tool_name = tool_call["name"]
        args      = tool_call.get("args", {})

        try:
            if args:
                result = coach_tool_map[tool_name](**args)
            else:
                result = coach_tool_map[tool_name]()
        except Exception as e:
            result = f"Tool error: {str(e)}"

        messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    final         = coach_llm_with_tools.invoke(messages)
    response_text = final.content

    append_to_session(session_key, [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": response_text},
    ])

    return response_text


# ============================================
# STUDENT RESPONSE
# ============================================

def generate_response(student_id, message, type, session_key):
    # Route coach messages to coach assistant
    if type == "coach":
        return coach_response(message, session_key)

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
            {"role": "user",      "content": message},
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
        args      = tool_call.get("args", {})

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
    final         = llm_with_tools.invoke(messages)
    response_text = final.content

    # Save to current session only (not Mem0 yet)
    append_to_session(session_key, [
        {"role": "user",      "content": message},
        {"role": "assistant", "content": response_text},
    ])

    return response_text