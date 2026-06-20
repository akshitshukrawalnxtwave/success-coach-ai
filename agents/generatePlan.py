# ============================================
# COACH TOOLS
# ============================================

from utils.sheets import db                  # FIX: was "from chromadb import db"
from utils.google_calendar import CALENDAR_ID, calendar_service

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

# Fixed time slots: 2pm to 6pm (4 slots x 1 hour each)
MEETING_SLOTS = ["14:00", "15:00", "16:00", "17:00"]


def add_event_to_calendar(
    student_id: str,
    event_type: str,
    date: str,
    slot_index: int
):
    """
    Creates a Google Calendar event only if the slot is free.

    Returns:
        {
            success: bool,
            message: str
        }
    """

    student = db.get_student_details(student_id)

    if not student:
        return {
            "success": False,
            "message": f"No student found with ID {student_id}"
        }

    slot = MEETING_SLOTS[slot_index % len(MEETING_SLOTS)]

    # Create timezone-aware datetimes
    start_dt = datetime.strptime(
        f"{date} {slot}",
        "%Y-%m-%d %H:%M"
    ).replace(tzinfo=IST)

    end_dt = start_dt + timedelta(hours=1)

    try:
        # ---------------------------------
        # CHECK EXISTING EVENTS
        # ---------------------------------
        existing = (
            calendar_service.events()
            .list(
                calendarId=CALENDAR_ID,
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        if existing.get("items"):
            return {
                "success": False,
                "message": (
                    f"Slot {slot} on {date} already occupied"
                )
            }

        # ---------------------------------
        # CREATE EVENT
        # ---------------------------------
        event_body = {
            "summary": f"{event_type} - {student['name']}",
            "description": (
                "Coaching Session\n"
                f"Student ID: {student_id}\n"
                f"Student: {student['name']}\n"
                f"Signal: {event_type}"
            ),
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
        }

        created = (
            calendar_service.events()
            .insert(
                calendarId=CALENDAR_ID,
                body=event_body
            )
            .execute()
        )

        return {
            "success": True,
            "message": (
                f"✅ Event created — "
                f"{student['name']} | "
                f"{slot}-{end_dt.strftime('%H:%M')}"
            ),
            "event_id": created["id"],
            "event_link": created.get("htmlLink")
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Calendar error: {str(e)}"
        }

def generate_plan():
    """
    Generate structured daily plan and auto-create Google Calendar events
    for today's highest-priority students. Marks each scheduled student's
    signal as actioned so they don't reappear in future plans.
    """
    print("Generating daily coaching plan...")
    all_signals = db.get_signals()
    unactioned = [s for s in all_signals if str(s.get('actioned')).strip() == 'No']

    if not unactioned:
        return "No pending signals. All students are on track."

    urgency_map  = {"High": 0, "Medium": 1, "Low": 2}
    severity_map = {"High": 0, "Medium": 1, "Low": 2}

    sorted_signals = sorted(
        unactioned,
        key=lambda x: (
            urgency_map.get(x.get('urgency'),  99),
            severity_map.get(x.get('severity'), 99)
        )
    )

    now_ist       = datetime.now(IST)
    today_date    = now_ist.strftime("%Y-%m-%d")
    tomorrow_date = (now_ist + timedelta(days=1)).strftime("%Y-%m-%d")

    # 4 students max today (one per hour slot), rest deferred to tomorrow
    today_signals    = sorted_signals[:4]
    tomorrow_signals = sorted_signals[4:]

    plan  = f"DAILY COACHING PLAN — {today_date}\n"
    plan += f"{'=' * 60}\n\n"
    plan += f"TODAY ({len(today_signals)} students) — Meetings 2 PM to 6 PM:\n\n"

    calendar_results = []

    for idx, sig in enumerate(today_signals):
        student    = db.get_student_details(sig.get('student_id'))
        slot_label = MEETING_SLOTS[idx]
        slot_end   = f"{int(slot_label[:2]) + 1}:00"
        student_name = (
            student.get('name', 'Unknown')
            if student
            else f"Unknown (ID: {sig.get('student_id')})"
        )

        plan += (
            f"{idx + 1}. {student_name} "
            f"[{slot_label}–{slot_end}]\n"
            f"   Type: {sig.get('signal_type')} | "
            f"Urgency: {sig.get('urgency')} | "
            f"Severity: {sig.get('severity')}\n"
            f"   Reason: {sig.get('reason')}\n\n"
        )

        # Create calendar event
        cal_result = add_event_to_calendar(
            student_id=sig.get('student_id'),
            event_type=sig.get('signal_type'),
            date=today_date,
            slot_index=idx
        )
        calendar_results.append(cal_result)

        # Mark signal as actioned so it won't reappear tomorrow
        db.mark_signal_actioned(sig.get('student_id'))

    if tomorrow_signals:
        plan += f"\nDEFERRED TO TOMORROW ({len(tomorrow_signals)} students):\n"
        for idx, sig in enumerate(tomorrow_signals, 1):
            student = db.get_student_details(sig.get('student_id'))
            student_name = (
                student.get('name', 'Unknown')
                if student
                else f"Unknown (ID: {sig.get('student_id')})"
            )
            plan += (
                f"{idx}. {student_name} "
                f"— Scheduled for {tomorrow_date}\n"
                f"   Type: {sig.get('signal_type')} | "
                f"Reason: {sig.get('reason')}\n"
            )

    plan += f"\n{'=' * 60}\n📅 CALENDAR EVENTS:\n"
    for r in calendar_results:
        plan += f"  {r['message']}\n"

        if r.get("event_link"):
            plan += f"     {r['event_link']}\n"

    return plan