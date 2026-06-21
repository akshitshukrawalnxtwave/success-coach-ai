from datetime import date

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

client = gspread.authorize(creds)

# Open spreadsheet
spreadsheet = client.open("SCAI")

# Open tabs by worksheet name
roster = spreadsheet.worksheet("roster")
attendance = spreadsheet.worksheet("attendance")
exam_scores = spreadsheet.worksheet("exam_scores")
exam_schedule = spreadsheet.worksheet("exam_schedule")
signal_sheet = spreadsheet.worksheet("signal_sheet")
events = spreadsheet.worksheet("events")


class Database:
    """Database class to manage all student data from Google Sheets"""

    def __init__(self):
        """Fetch all data from sheets on initialization"""
        self.roster_data = roster.get_all_records()
        self.attendance_data = attendance.get_all_records()
        self.exam_scores_data = exam_scores.get_all_records()
        self.exam_schedule_data = exam_schedule.get_all_records()
        self.signal_data = signal_sheet.get_all_records()
        self.events_data = events.get_all_records()

    def get_student_details(self, student_id):
        """Returns the details of the student with the given student_id"""
        for record in self.roster_data:
            if record.get('student_id') == student_id:
                return record
        return None

    def get_student_scores(self, student_id):
        """Returns the scores of the student with the given student_id"""
        scores = []
        for record in self.exam_scores_data:
            if record.get('student_id') == student_id:
                scores.append({
                    'subject': record.get('subject'),
                    'score': record.get('score'),
                    'max_score': record.get('max_score'),
                    'date': record.get('date')
                })
        return scores

    def get_student_attendance(self, student_id):
        """Returns the attendance of the student with the given student_id"""
        attendance_records = []
        for record in self.attendance_data:
            if record.get('student_id') == student_id:
                attendance_records.append({
                    'attendance_pct': record.get('attendance_pct'),
                    'week_of': record.get('week_of'),
                    'classes_attended': record.get('classes_attended'),
                    'classes_scheduled': record.get('classes_scheduled')
                })
        return attendance_records

    def get_exams_schedule(self, student_id):
        """Returns the exam schedule of the student with the given student_id"""
        exams = []
        for record in self.exam_schedule_data:
            if record.get('student_id') == student_id:
                exams.append({
                    'subject': record.get('subject'),
                    'exam_date': record.get('exam_date'),
                    'exam_type': record.get('exam_type')
                })
        return exams

    def get_all_students(self):
        """Fetch all students from roster"""
        students = []
        for record in self.roster_data:
            students.append({
                'id': record.get('student_id'),
                'name': record.get('name')
            })
        return students

    def get_student_info(self, student_id):
        """Get comprehensive student data"""
        return {
            'scores': self.get_student_scores(student_id),
            'attendance': self.get_student_attendance(student_id),
            'upcoming_exams': self.get_exams_schedule(student_id)
        }

    def save_signal(self, student_id, signal_type, severity, urgency, reason, timestamp, actioned):
        """Save a signal to the signal_sheet"""
        new_signal = [
            student_id,
            signal_type,
            severity,
            urgency,
            reason,
            timestamp,
            actioned
        ]
        try:
            signal_sheet.append_row(new_signal)
            # Add to in-memory data
            self.signal_data.append({
                'student_id': student_id,
                'signal_type': signal_type,
                'severity': severity,
                'urgency': urgency,
                'reason': reason,
                'timestamp': timestamp,
                'actioned': actioned
            })
            print(f"Signal saved for student {student_id}")
            return True
        except Exception as e:
            print(f"Error saving signal: {e}")
            return False

    def get_signals(self):
        """Fetch all signals from signal_sheet"""
        return self.signal_data

    def mark_signal_actioned(self, student_id):
        """
        Mark the first unactioned signal for a student as 'Yes' in both
        the Google Sheet and in-memory data.
        """
        try:
            for idx, record in enumerate(self.signal_data):
                if (
                    record.get('student_id') == student_id
                    and str(record.get('actioned')).strip() == 'No'
                ):
                    # Rows in the sheet: row 1 = header, data starts at row 2
                    sheet_row = idx + 2
                    # Column 7 = 'actioned' (matches save_signal column order)
                    signal_sheet.update_cell(sheet_row, 7, 'Yes')
                    # Mirror update in-memory
                    self.signal_data[idx]['actioned'] = 'Yes'
                    print(f"Signal marked actioned for student {student_id}")
                    return True

            print(f"No unactioned signal found for student {student_id}")
            return False
        except Exception as e:
            print(f"Error marking signal actioned: {e}")
            return False

    def delete_signal(self, student_id):
        """Delete a signal from the signal_sheet based on student_id"""
        try:
            for idx, record in enumerate(self.signal_data):
                if record.get('student_id') == student_id:
                    # +2: header row offset + 0-based index
                    signal_sheet.delete_row(idx + 2)
                    self.signal_data.pop(idx)
                    print(f"Signal deleted for student {student_id}")
                    return True
            print(f"No matching signal found for student {student_id}")
            return False
        except Exception as e:
            print(f"Error deleting signal: {e}")
            return False
    
    def get_sessions_by_date(self, date):
        return [
            row
            for row in self.events_data
            if str(row.get("session_date")) == date
        ]
    
    def is_student_scheduled(self, student_id, date):
        for row in self.events_data:
            if (
                row.get("student_id") == student_id
                and row.get("session_date") == date
                and row.get("status") in ["planned", "completed"]
            ):
                return True
        return False

    def save_session(
        self,
        session_id,
        student_id,
        session_date,
        slot_time,
        signal_type,
        status="planned"
    ):
        row = [
            session_id,
            student_id,
            session_date,
            slot_time,
            signal_type,
            status
        ]

        events.append_row(row)

        self.events_data.append({
            "session_id": session_id,
            "student_id": student_id,
            "session_date": session_date,
            "slot_time": slot_time,
            "signal_type": signal_type,
            "status": status
        })

        return True

    def get_free_slots(self, date, all_slots):

        occupied = {
            str(row["slot_time"])
            for row in self.events_data
            if (
                row["session_date"] == date
                and row["status"] in ["planned", "completed"]
            )
        }

        return [
            slot
            for slot in all_slots
            if slot not in occupied
        ]

# Initialize database instance
db = Database()