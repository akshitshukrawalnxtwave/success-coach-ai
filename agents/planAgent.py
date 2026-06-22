"""
Plan Agent — replaces generate_plan().

The agent can:
1. Generate today's coaching schedule from signals
2. Let the coach modify it via chat:
   - swap a student to a different slot
   - defer a student to tomorrow
   - cancel / remove a session
   - manually add a session
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool

from constants import OPEN_AI_MODEL
from utils.sheets import db
from utils.google_calendar import calendar_service, CALENDAR_ID

load_dotenv()

IST = ZoneInfo("Asia/Kolkata")

MEETING_SLOTS = ["14:00", "15:00", "16:00", "17:00"]


# ============================================
# INTERNAL HELPERS
# ============================================

def _now_today_tomorrow():
    now      = datetime.now(IST)
    today    = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    return now, today, tomorrow


def _create_calendar_event(student_id: str, event_type: str, date: str, slot: str) -> dict:
    """Low-level: create one Google Calendar event. Returns {success, event_id, event_link} or {success, message}."""
    student = db.get_student_details(student_id)
    if not student:
        return {"success": False, "message": f"Student not found: {student_id}"}

    start_dt = datetime.strptime(f"{date} {slot}", "%Y-%m-%d %H:%M").replace(tzinfo=IST)
    end_dt   = start_dt + timedelta(hours=1)

    event = {
        "summary":     f"{event_type} - {student['name']}",
        "description": f"Student ID: {student_id}",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
        "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "Asia/Kolkata"},
    }
    try:
        created = calendar_service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        return {"success": True, "event_id": created["id"], "event_link": created.get("htmlLink")}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _delete_calendar_event(event_id: str):
    try:
        calendar_service.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    except Exception as e:
        print(f"Calendar delete warning: {e}")


# ============================================
# PLAN AGENT TOOLS
# ============================================

def get_today_plan() -> str:
    """
    Read the current state of today's coaching schedule from Google Sheets.
    Returns a formatted plan showing each slot and who is booked (or FREE).
    Also lists pending unactioned signals that haven't been scheduled yet.
    Always call this first before making any modifications.
    """
    db.refresh_signals_and_events()
    _, today, tomorrow = _now_today_tomorrow()

    today_sessions = db.get_sessions_by_date(today)
    occupied = {
        s["slot_time"]: s
        for s in today_sessions
        if s["status"] in ["planned", "completed"]
    }

    lines = [f"DAILY PLAN — {today}", "=" * 50, ""]

    for slot in MEETING_SLOTS:
        row = occupied.get(slot)
        if row:
            student = db.get_student_details(row["student_id"])
            name    = student["name"] if student else row["student_id"]
            lines.append(f"{slot} → {name} | {row['signal_type']} [{row['status']}]")
        else:
            lines.append(f"{slot} → FREE")

    # Pending unscheduled signals
    all_signals = [
        s for s in db.get_signals()
        if str(s.get("actioned", "")).strip() == "No"
        and not db.is_student_scheduled(s["student_id"], today)
    ]

    if all_signals:
        lines += ["", "PENDING (not yet scheduled):", ""]
        for s in all_signals:
            student = db.get_student_details(s["student_id"])
            name    = student["name"] if student else s["student_id"]
            lines.append(
                f"- {name} | {s['signal_type']} "
                f"(Urgency: {s.get('urgency')}, Severity: {s.get('severity')})"
            )

    return "\n".join(lines)


def schedule_pending_students() -> str:
    """
    Auto-schedule all unactioned signals into free slots today.
    Prioritises by urgency then severity (High first).
    Creates Google Calendar events and saves sessions to the events sheet.
    Defers overflow students to tomorrow.
    Returns a summary of what was scheduled and what was deferred.
    """
    db.refresh_signals_and_events()
    _, today, tomorrow = _now_today_tomorrow()

    # Free slots
    today_sessions = db.get_sessions_by_date(today)
    occupied_slots = {
        s["slot_time"]
        for s in today_sessions
        if s["status"] in ["planned", "completed"]
    }
    free_slots = [s for s in MEETING_SLOTS if s not in occupied_slots]

    # Pending signals sorted by priority
    signals = [
        s for s in db.get_signals()
        if str(s.get("actioned", "")).strip() == "No"
        and not db.is_student_scheduled(s["student_id"], today)
    ]
    urgency_rank  = {"High": 0, "Medium": 1, "Low": 2}
    severity_rank = {"High": 0, "Medium": 1, "Low": 2}
    signals.sort(key=lambda x: (
        urgency_rank.get(x.get("urgency", ""), 99),
        severity_rank.get(x.get("severity", ""), 99),
    ))

    scheduled = []
    deferred  = []

    for idx, sig in enumerate(signals):
        if idx < len(free_slots):
            slot   = free_slots[idx]
            result = _create_calendar_event(sig["student_id"], sig["signal_type"], today, slot)
            if result["success"]:
                db.save_session(
                    session_id   = result["event_id"],
                    student_id   = sig["student_id"],
                    session_date = today,
                    slot_time    = slot,
                    signal_type  = sig["signal_type"],
                    status       = "planned",
                )
                db.mark_signal_actioned(sig["student_id"])
                student = db.get_student_details(sig["student_id"])
                name    = student["name"] if student else sig["student_id"]
                scheduled.append(f"  ✅ {slot} → {name} ({sig['signal_type']})")
            else:
                scheduled.append(f"  ❌ {slot} → booking failed: {result.get('message')}")
        else:
            student = db.get_student_details(sig["student_id"])
            name    = student["name"] if student else sig["student_id"]
            deferred.append(f"  - {name} ({sig['signal_type']})")

    lines = [f"SCHEDULE RESULT — {today}", ""]
    if scheduled:
        lines += ["Scheduled today:"] + scheduled
    else:
        lines.append("No new sessions scheduled (no free slots or no pending signals).")

    if deferred:
        lines += ["", f"Deferred to {tomorrow}:"] + deferred

    return "\n".join(lines)


def move_session(student_id: str, new_slot: str) -> str:
    """
    Move an existing session for a student to a different slot today.
    Cancels the old calendar event and creates a new one in the new slot.

    Args:
        student_id: The student's ID (e.g. 'STU002')
        new_slot: Target time slot in HH:MM 24-hour format. Must be one of: '14:00', '15:00', '16:00', '17:00'

    Returns:
        Confirmation message or error description.
    """
    db.refresh_signals_and_events()
    _, today, _ = _now_today_tomorrow()

    today_sessions = db.get_sessions_by_date(today)

    # Find student's current session
    current = next(
        (s for s in today_sessions
         if s["student_id"] == student_id and s["status"] in ["planned"]),
        None
    )
    if not current:
        student = db.get_student_details(student_id)
        name    = student["name"] if student else student_id
        return f"❌ No planned session found for {name} today."

    # Check new slot is free
    occupied_slots = {
        s["slot_time"]
        for s in today_sessions
        if s["status"] in ["planned", "completed"] and s["student_id"] != student_id
    }
    if new_slot not in MEETING_SLOTS:
        return f"❌ Invalid slot '{new_slot}'. Valid slots: {', '.join(MEETING_SLOTS)}"
    if new_slot in occupied_slots:
        return f"❌ Slot {new_slot} is already taken by another student."

    student     = db.get_student_details(student_id)
    name        = student["name"] if student else student_id
    old_slot    = current["slot_time"]
    signal_type = current["signal_type"]

    # Delete old calendar event
    _delete_calendar_event(current["session_id"])

    # Remove old session from in-memory
    db.events_data[:] = [
        r for r in db.events_data
        if not (
            r.get("student_id")   == student_id
            and r.get("session_date") == today
            and r.get("slot_time")    == old_slot
        )
    ]

    # Create new calendar event
    result = _create_calendar_event(student_id, signal_type, today, new_slot)
    if not result["success"]:
        return f"❌ Calendar error: {result.get('message')}"

    db.save_session(
        session_id   = result["event_id"],
        student_id   = student_id,
        session_date = today,
        slot_time    = new_slot,
        signal_type  = signal_type,
        status       = "planned",
    )

    return (
        f"✅ Moved {name} from {old_slot} → {new_slot} today.\n"
        f"Calendar event updated."
    )


def defer_student(student_id: str) -> str:
    """
    Remove a student's session from today and defer them to tomorrow.
    Cancels their Google Calendar event for today.

    Args:
        student_id: The student's ID (e.g. 'STU002')

    Returns:
        Confirmation message or error description.
    """
    db.refresh_signals_and_events()
    _, today, tomorrow = _now_today_tomorrow()

    today_sessions = db.get_sessions_by_date(today)

    current = next(
        (s for s in today_sessions
         if s["student_id"] == student_id and s["status"] == "planned"),
        None
    )

    student = db.get_student_details(student_id)
    name    = student["name"] if student else student_id

    if not current:
        return f"❌ No planned session found for {name} today."

    _delete_calendar_event(current["session_id"])

    # Remove from in-memory
    db.events_data[:] = [
        r for r in db.events_data
        if not (
            r.get("student_id")   == student_id
            and r.get("session_date") == today
        )
    ]

    # Unmark signal so they get picked up in tomorrow's plan
    for sig in db.signal_data:
        if sig.get("student_id") == student_id and str(sig.get("actioned", "")).strip() == "Yes":
            sig["actioned"] = "No"
            break

    return (
        f"✅ {name}'s session removed from today.\n"
        f"They will appear as pending for {tomorrow}'s plan."
    )


def add_session(student_id: str, slot: str, signal_type: str = "Other") -> str:
    """
    Manually add a coaching session for a student in a specific slot today.
    Use this when the coach wants to book a student who has no active signal.

    Args:
        student_id: The student's ID (e.g. 'STU002')
        slot: Time slot in HH:MM 24-hour format. Must be one of: '14:00', '15:00', '16:00', '17:00'
        signal_type: Type of session e.g. 'Academic', 'Attendance', 'Mental Health', 'Behavioral', 'Other'

    Returns:
        Confirmation message or error description.
    """
    db.refresh_signals_and_events()
    _, today, _ = _now_today_tomorrow()

    if slot not in MEETING_SLOTS:
        return f"❌ Invalid slot '{slot}'. Valid slots: {', '.join(MEETING_SLOTS)}"

    if db.is_student_scheduled(student_id, today):
        student = db.get_student_details(student_id)
        name    = student["name"] if student else student_id
        return f"❌ {name} is already scheduled today."

    today_sessions = db.get_sessions_by_date(today)
    occupied_slots = {
        s["slot_time"]
        for s in today_sessions
        if s["status"] in ["planned", "completed"]
    }
    if slot in occupied_slots:
        return f"❌ Slot {slot} is already taken."

    result = _create_calendar_event(student_id, signal_type, today, slot)
    if not result["success"]:
        return f"❌ Calendar error: {result.get('message')}"

    db.save_session(
        session_id   = result["event_id"],
        student_id   = student_id,
        session_date = today,
        slot_time    = slot,
        signal_type  = signal_type,
        status       = "planned",
    )

    student = db.get_student_details(student_id)
    name    = student["name"] if student else student_id

    return f"✅ {name} booked into {slot} today ({signal_type})."


def remove_session(student_id: str) -> str:
    """
    Cancel and remove a student's session from today entirely (no deferral).
    Deletes the Google Calendar event.

    Args:
        student_id: The student's ID (e.g. 'STU002')

    Returns:
        Confirmation message or error description.
    """
    db.refresh_signals_and_events()
    _, today, _ = _now_today_tomorrow()

    today_sessions = db.get_sessions_by_date(today)
    current = next(
        (s for s in today_sessions
         if s["student_id"] == student_id and s["status"] == "planned"),
        None
    )

    student = db.get_student_details(student_id)
    name    = student["name"] if student else student_id

    if not current:
        return f"❌ No planned session found for {name} today."

    _delete_calendar_event(current["session_id"])

    db.events_data[:] = [
        r for r in db.events_data
        if not (
            r.get("student_id")   == student_id
            and r.get("session_date") == today
        )
    ]

    return f"✅ Session for {name} cancelled and removed from today's plan."


# ============================================
# TOOL REGISTRY
# ============================================

plan_tools = [
    StructuredTool.from_function(get_today_plan),
    StructuredTool.from_function(schedule_pending_students),
    StructuredTool.from_function(move_session),
    StructuredTool.from_function(defer_student),
    StructuredTool.from_function(add_session),
    StructuredTool.from_function(remove_session),
]

plan_tool_map = {
    "get_today_plan":            get_today_plan,
    "schedule_pending_students": schedule_pending_students,
    "move_session":              move_session,
    "defer_student":             defer_student,
    "add_session":               add_session,
    "remove_session":            remove_session,
}

PLAN_SYSTEM_PROMPT = """
You are a coaching plan assistant. You help the coach view and modify today's session schedule.

TOOLS:
1. get_today_plan            — View the current schedule for today (slots + who is booked).
                               Always call this first before any modification.
2. schedule_pending_students — Auto-schedule all pending unactioned signals into free slots today.
                               Call this when coach says "generate plan", "start my day",
                               "who do I meet", "schedule today", "what's my plan".
3. move_session              — Move a student to a different time slot today.
                               Requires student_id and new_slot (e.g. '15:00').
4. defer_student             — Remove a student from today and push them to tomorrow.
                               Requires student_id.
5. add_session               — Manually add any student to a slot today.
                               Requires student_id, slot, and optionally signal_type.
6. remove_session            — Cancel a student's session today with no deferral.
                               Requires student_id.

RULES:
- Always call get_today_plan first to see the current state before making changes.
- For move/defer/add/remove: resolve student names to student_id using context.
  If the coach says a name (e.g. "move Rahul to 15:00"), look up the student_id from
  the plan output or ask the coach to confirm the student_id.
- After every modification, call get_today_plan again to show the updated schedule.
- Never show raw JSON or dicts.
- Be concise. Confirm every change clearly.
- If a requested slot is taken, tell the coach which student is in it and ask what to do.
"""


# ============================================
# PLAN AGENT ENTRY POINT
# ============================================

def plan_agent(message: str, session_messages: list = None) -> str:
    """
    Plan agent entry point. Replaces generate_plan().

    Args:
        message: Coach's message (e.g. "generate plan", "swap STU002 to 15:00")
        session_messages: Prior messages in this session for context.

    Returns:
        Agent's response as a string.
    """
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

    llm = ChatOpenAI(model=OPEN_AI_MODEL, temperature=0.2)
    llm_with_tools = llm.bind_tools(plan_tools)

    messages = [SystemMessage(content=PLAN_SYSTEM_PROMPT)]

    # Inject prior session context so agent remembers previous plan output
    if session_messages:
        for item in (session_messages[-10:]):
            role    = item.get("role")
            content = item.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=message))

    # Agentic loop — keep going until no more tool calls
    for _ in range(6):  # max 6 iterations to prevent infinite loops
        ai_msg = llm_with_tools.invoke(messages)
        messages.append(ai_msg)

        if not ai_msg.tool_calls:
            return ai_msg.content

        for tool_call in ai_msg.tool_calls:
            tool_name = tool_call["name"]
            args      = tool_call.get("args", {})
            try:
                fn     = plan_tool_map[tool_name]
                result = fn(**args) if args else fn()
            except Exception as e:
                result = f"Tool error ({tool_name}): {str(e)}"

            messages.append(
                ToolMessage(content=str(result), tool_call_id=tool_call["id"])
            )

    return "I wasn't able to complete the plan operation. Please try again."