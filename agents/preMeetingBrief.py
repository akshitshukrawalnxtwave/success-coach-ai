"""Pre-meeting brief tool for coaches."""

from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from constants import OPEN_AI_MODEL
from utils.prevChat import fetch_factual_memories, fetch_session_summaries
from utils.sheets import db

load_dotenv()

_llm = ChatOpenAI(model=OPEN_AI_MODEL, temperature=0.3)


def _format_scores(scores: list) -> str:
    if not scores:
        return "No score data"
    recent = scores[-3:]
    return "\n".join(
        f"- {s.get('subject')}: {s.get('score')}/{s.get('max_score')} on {s.get('date')}"
        for s in recent
    )


def _format_attendance(attendance: list) -> str:
    if not attendance:
        return "No attendance data"
    recent = attendance[-3:]
    return "\n".join(
        f"- Week of {a.get('week_of')}: {a.get('attendance_pct')}% "
        f"({a.get('classes_attended')}/{a.get('classes_scheduled')} classes)"
        for a in recent
    )


def _format_exams(exams: list) -> str:
    if not exams:
        return "No upcoming exams"
    today = datetime.now().date()
    lines = []
    for exam in exams:
        exam_date = exam.get("exam_date")
        try:
            days_until = (
                datetime.strptime(str(exam_date), "%Y-%m-%d").date() - today
            ).days
            urgency = f"in {days_until} days" if days_until >= 0 else "past"
        except ValueError:
            urgency = "date unknown"
        lines.append(
            f"- {exam.get('subject')} ({exam.get('exam_type')}) on {exam_date} — {urgency}"
        )
    return "\n".join(lines)


def _format_signals(signals: list) -> str:
    if not signals:
        return "No active signals"
    return "\n".join(
        f"- [{s.get('signal_type')}] urgency={s.get('urgency')}, "
        f"severity={s.get('severity')}, actioned={s.get('actioned')}\n"
        f"  Reason: {s.get('reason')}"
        for s in signals
    )


def _format_memories(memories: list, label: str) -> str:
    if not memories:
        return f"No {label} available"
    return "\n".join(
        f"- {m.get('content', '')[:400]}"
        for m in memories
    )


def _gather_brief_context(student_id: str) -> dict | str:
    student = db.get_student_details(student_id)
    if not student:
        return f"No student found with ID {student_id}"

    scores = db.get_student_scores(student_id)
    attendance = db.get_student_attendance(student_id)
    exams = db.get_exams_schedule(student_id)
    all_signals = [
        s for s in db.get_signals()
        if s.get("student_id") == student_id
    ]
    open_signals = [
        s for s in all_signals
        if str(s.get("actioned", "")).strip().lower() == "no"
    ]

    return {
        "student": student,
        "scores": scores,
        "attendance": attendance,
        "exams": exams,
        "open_signals": open_signals,
        "all_signals": all_signals,
        "session_summaries": fetch_session_summaries(student_id),
        "factual_memories": fetch_factual_memories(student_id),
    }


def _resolve_student_id(student_id_or_name: str) -> str:
    if db.get_student_details(student_id_or_name):
        return student_id_or_name

    query = student_id_or_name.strip().lower()
    for student in db.get_all_students():
        if student.get("id", "").lower() == query:
            return student["id"]
        if student.get("name", "").lower() == query:
            return student["id"]
    return student_id_or_name


def get_pre_meeting_brief(student_id: str) -> str:
    """
    Build a focused pre-meeting brief for a student using sheet data,
    Mem0 factual memory, and stored session summaries.
    """
    student_id = _resolve_student_id(student_id)
    context = _gather_brief_context(student_id)
    if isinstance(context, str):
        return context

    student = context["student"]
    student_name = student.get("name", student_id)

    raw_context = f"""STUDENT PROFILE
Name: {student_name}
ID: {student_id}
Program: {student.get('program')} | Cohort: {student.get('cohort')}
Manager: {student.get('manager_email')}

EXAM SCORES (recent)
{_format_scores(context['scores'])}

ATTENDANCE (recent)
{_format_attendance(context['attendance'])}

UPCOMING EXAMS
{_format_exams(context['exams'])}

OPEN SIGNALS / CONCERNS
{_format_signals(context['open_signals'])}

ALL SIGNAL HISTORY
{_format_signals(context['all_signals'])}

SESSION SUMMARIES (from past ended sessions)
{_format_memories(context['session_summaries'], 'session summaries')}

FACTUAL MEMORY (from Mem0)
{_format_memories(context['factual_memories'], 'factual memory')}
"""

    system_prompt = """You are a student success coach assistant preparing a pre-meeting brief.
Using ONLY the provided data, write a concise, actionable brief with exactly these sections:

1. CURRENT ACADEMIC SITUATION
   - Summarise scores, attendance, and upcoming exams in plain language.

2. WHAT HAS CHANGED SINCE LAST SESSION
   - Compare recent data and session summaries to highlight deltas, trends, or new issues.
   - If no prior session summary exists, state that clearly.

3. OPEN CONCERNS
   - List unresolved signals, risk flags, or follow-ups from memory/summaries.

4. CONVERSATION STARTERS FOR TODAY
   - Provide 3-5 specific, natural questions the coach can ask in today's meeting.
   - Tie each starter to real data from the context.

Rules:
- Be factual. Do not invent details.
- Keep the full brief under 350 words.
- Use bullet points within sections.
- Do not output JSON."""

    try:
        response = _llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=raw_context),
        ])
        brief_body = (response.content or "").strip()
    except Exception as e:
        return f"Could not generate pre-meeting brief: {e}"

    header = (
        f"PRE-MEETING BRIEF — {student_name} ({student_id})\n"
        f"{'=' * 55}\n\n"
    )
    return header + brief_body
