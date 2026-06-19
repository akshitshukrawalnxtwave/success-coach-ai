from langchain.tools import tool
from utils.sheets import db


@tool
def get_student_details(student_id: str):
    """Get basic details for a student"""
    return db.get_student_details(student_id)

@tool
def get_all_student_details():
    """Return a compact list of all students"""
    return db.get_all_students()


@tool
def get_student_scores(student_id: str):
    """Get exam scores for a student"""
    return db.get_student_scores(student_id)


@tool
def get_student_attendance(student_id: str):
    """Get attendance information for a student"""
    return db.get_student_attendance(student_id)


@tool
def get_exam_schedule(student_id: str):
    """Get upcoming exam schedule for a student"""
    return db.get_exams_schedule(student_id)

@tool
def save_signal(student_id: str, signal_type: str, severity: int, urgency: int, reason: str, timestamp: str, actioned: bool):
    """Save a signal for a student"""
    return db.save_signal(student_id, signal_type, severity, urgency, reason, timestamp, actioned)
