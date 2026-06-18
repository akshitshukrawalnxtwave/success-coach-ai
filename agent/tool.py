from langchain.tools import tool
from sheets import db


@tool
def get_student_details(student_id: str):
    """Get basic details for a student"""
    return db.get_student_details(student_id)


@tool
def get_student_scores(student_id: str):
    """Get exam scores for a student"""
    return db.get_student_scores(student_id)


@tool
def get_student_attendance(student_id: str):
    """Get attendance information for a student"""
    print(db.get_student_attendance(student_id))
    return db.get_student_attendance(student_id)


@tool
def get_exam_schedule(student_id: str):
    """Get upcoming exam schedule for a student"""
    return db.get_exams_schedule(student_id)