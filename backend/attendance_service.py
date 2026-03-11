import datetime
from sqlalchemy.orm import Session
from .database import Student, AttendanceRecord, AllowedNetwork
from .face_engine import FaceEngine
from .ip_validator import is_ip_allowed

engine = FaceEngine()

def register_student(db: Session, name: str, roll_number: str, email: str, password_hash: str, front_image: str, left_image: str, right_image: str) -> Student:
    """
    Registers a new student, extracts face embeddings from 3 angles, averages them for a robust encoding,
    and stores them in the database.
    """
    # Check if student already exists
    if db.query(Student).filter((Student.roll_number == roll_number) | (Student.email == email)).first():
        raise ValueError("Student with this roll number or email already exists.")
        
    try:
        # Extract encodings
        front_enc = engine.get_face_embedding(front_image)
        # For simplicity, we can do left and right too and average, but face_recognition
        # from a single 2D image is sometimes enough. Let's do all 3 and average them.
        left_enc = engine.get_face_embedding(left_image)
        right_enc = engine.get_face_embedding(right_image)
        
        # Average the 128-dimensional vectors
        avg_enc = [(f + l + r) / 3.0 for f, l, r in zip(front_enc, left_enc, right_enc)]
    except Exception as e:
        raise ValueError(f"Failed to process face images during registration: {str(e)}")

    new_student = Student(
        name=name,
        roll_number=roll_number,
        email=email,
        password_hash=password_hash,
        face_encoding=avg_enc,
        is_registered=True
    )
    
    db.add(new_student)
    db.commit()
    db.refresh(new_student)
    return new_student

def verify_and_mark_attendance(db: Session, student_id: int, client_ip: str, captured_image: str) -> AttendanceRecord:
    """
    Verifies IP and Face, then marks attendance for the day.
    """
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise ValueError("Student not found.")
        
    if not student.face_encoding:
        raise ValueError("Student face not registered.")

    # 1. IP Validation
    networks_db = db.query(AllowedNetwork).all()
    allowed_cidrs = [net.network_cidr for net in networks_db]
    
    if not is_ip_allowed(client_ip, allowed_cidrs):
        raise PermissionError(f"Access Denied: Your IP address ({client_ip}) is not on the college network.")

    # 2. Face Verification
    # Extract encoding from captured image
    try:
        captured_enc = engine.get_face_embedding(captured_image)
    except Exception as e:
        raise ValueError(f"Face verification failed: {str(e)}")

    if not engine.compare_faces(student.face_encoding, captured_enc):
        raise PermissionError("Face verification failed: The captured face does not match the registered student.")
        
    # 3. Mark Attendance
    today = datetime.date.today()
    now_time = datetime.datetime.now().time()
    
    # Check if already marked today
    existing_record = db.query(AttendanceRecord).filter(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.date == today
    ).first()
    
    if existing_record:
        # Update time to latest if they mark again, or just leave it. Let's just return it.
        return existing_record
        
    new_record = AttendanceRecord(
        student_id=student.id,
        date=today,
        time=now_time,
        status="PRESENT",
        ip_address=client_ip
    )
    
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return new_record

def periodic_presence_check(db: Session, student_id: int, client_ip: str, captured_image: str):
    """
    Silent verification logic for periodic checks. Similar logic, but logs failures differently.
    """
    try:
        verify_and_mark_attendance(db, student_id, client_ip, captured_image)
        return {"status": "success", "message": "Presence confirmed."}
    except Exception as e:
        # In a real system, you might increment an 'absence strikes' counter here
        return {"status": "failed", "reason": str(e)}
