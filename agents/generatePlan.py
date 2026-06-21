from utils.sheets import db
from utils.google_calendar import calendar_service, CALENDAR_ID

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MEETING_SLOTS = [
    "14:00",
    "15:00",
    "16:00",
    "17:00"
]


# ============================================
# CREATE CALENDAR EVENT
# ============================================

def add_event_to_calendar(
    student_id: str,
    event_type: str,
    date: str,
    slot: str
) -> dict:
    """
    Add a single coaching session to Google Calendar.

    Args:
        student_id: The student's ID (e.g. 'STU002')
        event_type: Type of session (e.g. 'Academic', 'Mental Health')
        date: Date in YYYY-MM-DD format (e.g. '2026-06-20')
        slot: Time in HH:MM 24-hour format. Must be one of: '14:00', '15:00', '16:00', '17:00'

    Returns:
        dict with success status and event details
    """

    student = db.get_student_details(student_id)

    if not student:
        return {
            "success": False,
            "message": f"Student not found: {student_id}"
        }

    start_dt = (
        datetime.strptime(
            f"{date} {slot}",
            "%Y-%m-%d %H:%M"
        )
        .replace(tzinfo=IST)
    )

    end_dt = start_dt + timedelta(hours=1)

    try:

        event = {
            "summary": (
                f"{event_type}"
                f" - "
                f"{student['name']}"
            ),
            "description": (
                f"Student ID: {student_id}"
            ),
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Kolkata"
            },
            "end": {
                "dateTime": end_dt.isoformat(),
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

        return {
            "success": True,
            "event_id": created["id"],
            "event_link": created.get(
                "htmlLink"
            )
        }

    except Exception as e:

        return {
            "success": False,
            "message": str(e)
        }


# ============================================
# GENERATE PLAN
# ============================================

def generate_plan():
    """
    Generate today's coaching schedule.

    - Load already scheduled sessions from events sheet
    - Find free slots
    - Schedule unfinished student signals
    - Create calendar events
    - Save sessions to events sheet
    - Move overflow students to tomorrow

    Returns:
        str: formatted coaching plan
    """

    now = datetime.now(IST)

    today = now.strftime(
        "%Y-%m-%d"
    )

    tomorrow = (
        now
        + timedelta(days=1)
    ).strftime(
        "%Y-%m-%d"
    )

    plan = (
        f"DAILY PLAN — {today}\n"
        + "=" * 60
        + "\n\n"
    )

    # --------------------------
    # EXISTING SESSIONS
    # --------------------------

    existing = (
        db.get_sessions_by_date(
            today
        )
    )

    occupied = {
        s["slot_time"]: s
        for s in existing
        if s["status"]
        in [
            "planned",
            "completed"
        ]
    }

    free_slots = []

    for slot in MEETING_SLOTS:

        if slot not in occupied:
            free_slots.append(
                slot
            )

    # --------------------------
    # GET SIGNALS
    # --------------------------

    signals = [
        s
        for s
        in db.get_signals()
        if (
            str(
                s.get(
                    "actioned"
                )
            ).strip()
            == "No"
        )
    ]

    urgency = {
        "High": 0,
        "Medium": 1,
        "Low": 2
    }

    severity = {
        "High": 0,
        "Medium": 1,
        "Low": 2
    }

    signals.sort(
        key=lambda x: (
            urgency.get(
                x["urgency"],
                99
            ),
            severity.get(
                x["severity"],
                99
            )
        )
    )

    pending = []

    for s in signals:

        if not db.is_student_scheduled(
            s["student_id"],
            today
        ):
            pending.append(
                s
            )

    scheduled = []

    # --------------------------
    # CREATE NEW EVENTS
    # --------------------------

    for idx, sig in enumerate(
        pending[:len(free_slots)]
    ):

        slot = free_slots[idx]

        result = (
            add_event_to_calendar(
                sig["student_id"],
                sig["signal_type"],
                today,
                slot
            )
        )

        if result["success"]:

            db.save_session(
                session_id=result[
                    "event_id"
                ],
                student_id=sig[
                    "student_id"
                ],
                session_date=today,
                slot_time=slot,
                signal_type=sig[
                    "signal_type"
                ],
                status="planned"
            )

            db.mark_signal_actioned(
                sig[
                    "student_id"
                ]
            )

            student = (
                db.get_student_details(
                    sig[
                        "student_id"
                    ]
                )
            )

            scheduled.append({

                "student": student,

                "slot": slot,

                "signal": sig,

                "link": result[
                    "event_link"
                ]
            })

    # --------------------------
    # REFRESH EVENTS
    # --------------------------

    today_sessions = (
        db.get_sessions_by_date(
            today
        )
    )

    plan += (
        "TODAY\n\n"
    )

    for slot in MEETING_SLOTS:

        row = None

        for s in today_sessions:

            if s[
                "slot_time"
            ] == slot:

                row = s
                break

        if row:

            student = (
                db.get_student_details(
                    row[
                        "student_id"
                    ]
                )
            )

            name = (
                student["name"]
                if student
                else "Unknown"
            )

            plan += (
                f"{slot}"
                f" → "
                f"{name}"
                f" | "
                f"{row['signal_type']}"
                "\n"
            )

        else:

            plan += (
                f"{slot}"
                " → FREE\n"
            )

    # --------------------------
    # TOMORROW
    # --------------------------

    remaining = pending[
        len(free_slots):
    ]

    if remaining:

        plan += (
            "\n\n"
            f"DEFERRED TO {tomorrow}\n\n"
        )

        for s in remaining:

            student = (
                db.get_student_details(
                    s[
                        "student_id"
                    ]
                )
            )

            name = (
                student[
                    "name"
                ]
                if student
                else "Unknown"
            )

            plan += (
                f"- "
                f"{name}"
                "\n"
            )

    return plan


# ============================================
# M9 — REPLAN FOR URGENT SIGNAL
# ============================================

def _is_high_priority(signal: dict) -> bool:
    """Return True if signal is High urgency OR High severity."""
    return (
        signal.get("urgency") == "High"
        or signal.get("severity") == "High"
    )


def replan_for_urgent_signal(
    new_student_id: str,
    new_signal: dict
) -> dict:
    """
    Called immediately after a new High-urgency/severity signal is saved.

    Behaviour:
    - If a free slot exists today  → book it, return summary of change.
    - If all slots are taken by non-critical students → bump the lowest-priority
      one to tomorrow and give the urgent student their slot.
    - If all slots are taken by equally critical students → surface a conflict
      to the coach and ask them to decide; do NOT auto-book.
    - If student is already scheduled today → no change needed.

    Returns:
        {
            "action":  "booked" | "bumped" | "conflict" | "already_scheduled" | "error",
            "message": str,           # human-readable summary for the coach
            "conflict_students": [],  # only when action == "conflict"
            "booked_slot": str | None,
            "bumped_student": str | None,
        }
    """

    now   = datetime.now(IST)
    today = now.strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    new_student = db.get_student_details(new_student_id)
    new_name    = new_student["name"] if new_student else new_student_id

    # Already scheduled today?
    if db.is_student_scheduled(new_student_id, today):
        return {
            "action":            "already_scheduled",
            "message":           f"⚠️ {new_name} already has a session today — no change needed.",
            "conflict_students": [],
            "booked_slot":       None,
            "bumped_student":    None,
        }

    today_sessions = db.get_sessions_by_date(today)

    occupied = {
        s["slot_time"]: s
        for s in today_sessions
        if s["status"] in ["planned", "completed"]
    }

    free_slots = [s for s in MEETING_SLOTS if s not in occupied]

    # ── Case 1: free slot available ──────────────────────────────────────────
    if free_slots:
        slot   = free_slots[0]
        result = add_event_to_calendar(
            new_student_id,
            new_signal["signal_type"],
            today,
            slot
        )

        if not result["success"]:
            return {
                "action":            "error",
                "message":           f"❌ Calendar error: {result.get('message')}",
                "conflict_students": [],
                "booked_slot":       None,
                "bumped_student":    None,
            }

        db.save_session(
            session_id   = result["event_id"],
            student_id   = new_student_id,
            session_date = today,
            slot_time    = slot,
            signal_type  = new_signal["signal_type"],
            status       = "planned"
        )
        db.mark_signal_actioned(new_student_id)

        return {
            "action":      "booked",
            "message": (
                f"✅ **Plan updated** — {new_name} added to {slot} slot today.\n"
                f"**Reason:** {new_signal.get('signal_type')} signal "
                f"(Urgency: {new_signal.get('urgency')}, "
                f"Severity: {new_signal.get('severity')})\n"
                f"**Why:** {new_signal.get('reason', 'No reason provided')}"
            ),
            "conflict_students": [],
            "booked_slot":       slot,
            "bumped_student":    None,
        }

    # ── Case 2: all slots taken — find a bump candidate ─────────────────────
    # A bump candidate is a student whose signal is NOT high priority
    # (i.e. Medium/Low urgency AND Medium/Low severity).
    all_signals = {
        s["student_id"]: s
        for s in db.get_signals()
    }

    bump_candidate_slot   = None
    bump_candidate_session = None

    for slot in MEETING_SLOTS:
        session = occupied.get(slot)
        if not session:
            continue
        if session["status"] == "completed":
            continue   # never bump a completed session

        sid    = session["student_id"]
        sig    = all_signals.get(sid, {})
        if not _is_high_priority(sig):
            bump_candidate_slot    = slot
            bump_candidate_session = session
            break

    if bump_candidate_slot:
        bumped_sid     = bump_candidate_session["student_id"]
        bumped_student = db.get_student_details(bumped_sid)
        bumped_name    = bumped_student["name"] if bumped_student else bumped_sid

        # Cancel the existing calendar event
        try:
            calendar_service.events().delete(
                calendarId=CALENDAR_ID,
                eventId=bump_candidate_session["session_id"]
            ).execute()
        except Exception as e:
            print(f"Could not delete calendar event for {bumped_sid}: {e}")

        # Remove from events sheet in-memory & mark unactioned so they get
        # picked up on next replan (sheets.py delete_signal covers signal;
        # for session we just update status to 'cancelled' in-memory)
        db.events_data[:] = [
            r for r in db.events_data
            if not (
                r.get("student_id")   == bumped_sid
                and r.get("session_date") == today
                and r.get("slot_time")    == bump_candidate_slot
            )
        ]

        # Book the urgent student into the freed slot
        result = add_event_to_calendar(
            new_student_id,
            new_signal["signal_type"],
            today,
            bump_candidate_slot
        )

        if not result["success"]:
            return {
                "action":            "error",
                "message":           f"❌ Calendar error after bump: {result.get('message')}",
                "conflict_students": [],
                "booked_slot":       None,
                "bumped_student":    bumped_name,
            }

        db.save_session(
            session_id   = result["event_id"],
            student_id   = new_student_id,
            session_date = today,
            slot_time    = bump_candidate_slot,
            signal_type  = new_signal["signal_type"],
            status       = "planned"
        )
        db.mark_signal_actioned(new_student_id)

        return {
            "action": "bumped",
            "message": (
                f"🔄 **Plan updated** — {new_name} moved into {bump_candidate_slot} slot.\n"
                f"**{bumped_name}** has been deferred to tomorrow ({tomorrow}).\n\n"
                f"**Why {new_name} takes priority:**\n"
                f"Signal: {new_signal.get('signal_type')} | "
                f"Urgency: {new_signal.get('urgency')} | "
                f"Severity: {new_signal.get('severity')}\n"
                f"Reason: {new_signal.get('reason', 'No reason provided')}\n\n"
                f"**Why {bumped_name} was deferred:**\n"
                f"Their signal is lower priority (not High urgency or severity)."
            ),
            "conflict_students": [],
            "booked_slot":       bump_candidate_slot,
            "bumped_student":    bumped_name,
        }

    # ── Case 3: all slots taken by equally critical students ─────────────────
    # Surface to coach — do NOT auto-decide.
    conflict_names = []
    for slot in MEETING_SLOTS:
        session = occupied.get(slot)
        if session:
            s       = db.get_student_details(session["student_id"])
            s_name  = s["name"] if s else session["student_id"]
            sig     = all_signals.get(session["student_id"], {})
            conflict_names.append({
                "name":      s_name,
                "slot":      slot,
                "urgency":   sig.get("urgency", "?"),
                "severity":  sig.get("severity", "?"),
                "signal_type": sig.get("signal_type", "?"),
            })

    conflict_lines = "\n".join(
        f"  • {c['slot']} → {c['name']} "
        f"({c['signal_type']}, U:{c['urgency']}, S:{c['severity']})"
        for c in conflict_names
    )

    return {
        "action": "conflict",
        "message": (
            f"⚠️ **Coach decision needed** — all slots today are taken by "
            f"high-priority students.\n\n"
            f"**New urgent signal:** {new_name} "
            f"({new_signal.get('signal_type')}, "
            f"Urgency: {new_signal.get('urgency')}, "
            f"Severity: {new_signal.get('severity')})\n"
            f"Reason: {new_signal.get('reason', 'No reason provided')}\n\n"
            f"**Current schedule (all critical):**\n{conflict_lines}\n\n"
            f"Who should be deferred to tomorrow to make room for {new_name}? "
            f"Reply with their name or tell me to defer {new_name} to tomorrow instead."
        ),
        "conflict_students": conflict_names,
        "booked_slot":       None,
        "bumped_student":    None,
    }