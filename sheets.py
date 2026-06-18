import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    "credentials.json",
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


class Database:
    """Database class to manage all student data from Google Sheets"""
    
    def __init__(self):
        """Fetch all data from sheets on initialization"""
        self.roster_data = roster.get_all_records()
        self.attendance_data = attendance.get_all_records()
        self.exam_scores_data = exam_scores.get_all_records()
        self.exam_schedule_data = exam_schedule.get_all_records()
    
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
        for record in self.attendance_data:
            if record.get('student_id') == student_id:
                return {
                    'attendance_pct': record.get('attendance_pct'),
                    'week_of': record.get('week_of'),
                    'classes_attended': record.get('classes_attended'),
                    'classes_scheduled': record.get('classes_scheduled')
                }
        return None
    
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


# Initialize database instance
db = Database()