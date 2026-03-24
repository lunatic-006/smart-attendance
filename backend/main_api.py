import io
import csv
import datetime
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from .database import get_db, init_db
from .attendance_service import register_user, verify_and_mark_attendance, periodic_presence_check

app = FastAPI(title="Smart Face Recognition Attendance API (MongoDB Backend)")

# Setup CORS for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Schemas
class UserRegistrationReq(BaseModel):
    role: str
    name: str
    id_number: str
    email: str
    passwordHash: str
    front_image: str
    left_image: str
    right_image: str

class AttendanceMarkReq(BaseModel):
    student_id: str
    target_lecturer_id: str
    captured_image: str

class PeriodicPingReq(BaseModel):
    student_id: str
    target_lecturer_id: str
    captured_image: str

@app.on_event("startup")
def on_startup():
    init_db()

@app.post("/api/register")
def api_register_user(req: UserRegistrationReq, db = Depends(get_db)):
    try:
        user = register_user(
            db=db, 
            role=req.role,
            name=req.name, 
            id_number=req.id_number, 
            email=req.email, 
            password_hash=req.passwordHash,
            front_image=req.front_image, 
            left_image=req.left_image, 
            right_image=req.right_image
        )
        return {"message": "Registration successful", "user_id": str(user["_id"])}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/login/student")
def api_login_student(roll_number: str, password_hash: str, db = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM students WHERE roll_number=? AND password_hash=?", (roll_number, password_hash))
    student = cursor.fetchone()
    
    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Login successful", "student_id": str(student["id"]), "name": student["name"]}

@app.post("/api/login/lecturer")
def api_login_lecturer(lecturer_id: str, password: str, db = Depends(get_db)):
    cursor = db.cursor()
    # Schema uses email, so we map lecturer_id to email for login
    cursor.execute("SELECT * FROM lecturers WHERE email=? AND password_hash=?", (lecturer_id, password))
    lecturer = cursor.fetchone()
    
    if not lecturer:
        # For testing, if no lecturer exists, let's hardcode an admin pass
        if lecturer_id == "admin" and password == "admin":
            return {"message": "Admin login auto-generated", "lecturer_id": "admin", "name": "System Admin"}
        raise HTTPException(status_code=401, detail="Invalid lecturer credentials")
    
    return {"message": "Login successful", "lecturer_id": str(lecturer["id"]), "name": lecturer["name"]}

@app.post("/api/attendance/mark")
def api_mark_attendance(req: AttendanceMarkReq, db = Depends(get_db)):
    try:
        record = verify_and_mark_attendance(
            db=db,
            student_id=req.student_id,
            target_lecturer_id=req.target_lecturer_id,
            captured_image=req.captured_image
        )
        return {"message": "Attendance actively processed.", "status": record["status"]}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/attendance/ping")
def api_periodic_ping(req: PeriodicPingReq, db = Depends(get_db)):
    result = periodic_presence_check(
        db=db,
        student_id=req.student_id,
        target_lecturer_id=req.target_lecturer_id,
        captured_image=req.captured_image
    )
    if result.get("status") == "failed":
        return JSONResponse(status_code=400, content=result)
    return result

# Lecturer Endpoints
@app.post("/api/dev/seed-class")
def api_seed_class(lecturer_id: int, class_name: str, duration_minutes: int, db = Depends(get_db)):
    """Creates an active class right now for testing."""
    cursor = db.cursor()
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    start_time_str = now.strftime("%H:%M:%S")
    end_time = now + datetime.timedelta(minutes=duration_minutes)
    end_time_str = end_time.strftime("%H:%M:%S")
    
    # 1 ping per minute expected
    expected_pings = duration_minutes
    
    cursor.execute("""
        INSERT INTO class_sessions (lecturer_id, class_name, date, start_time, end_time, total_expected_pings) 
        VALUES (?, ?, ?, ?, ?, ?)
    """, (lecturer_id, class_name, today_str, start_time_str, end_time_str, expected_pings))
    db.commit()
    
    return {"message": "Active class created successfully.", "session_id": cursor.lastrowid}

@app.get("/api/lecturer/sessions")
def api_get_sessions(lecturer_id: int, db = Depends(get_db)):
    """Fetches today's classes for the lecturer."""
    cursor = db.cursor()
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    cursor.execute("SELECT * FROM class_sessions WHERE lecturer_id=? AND date=?", (lecturer_id, today_str))
    sessions = cursor.fetchall()
    return {"sessions": [dict(s) for s in sessions]}

@app.get("/api/lecturer/session/{session_id}/report")
def api_get_session_report(session_id: int, db = Depends(get_db)):
    """Returns Present, Suspicious, Absent lists based on thresholds."""
    cursor = db.cursor()
    
    # Get session details
    cursor.execute("SELECT * FROM class_sessions WHERE id=?", (session_id,))
    session = cursor.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
        
    expected_pings = float(session["total_expected_pings"])
    threshold = 0.8 * expected_pings if expected_pings > 0 else 0
    
    # Get all registered students
    cursor.execute("SELECT id, name, roll_number FROM students")
    all_students = cursor.fetchall()
    
    # Get attendance records for this session
    cursor.execute("SELECT student_id, ping_count FROM attendance_records WHERE session_id=?", (session_id,))
    records = cursor.fetchall()
    record_map = {r["student_id"]: r["ping_count"] for r in records}
    
    present_list = []
    suspicious_list = []
    absent_list = []
    
    for s in all_students:
        s_id = s["id"]
        ping_count = record_map.get(s_id, 0)
        
        student_data = {"id": s_id, "name": s["name"], "roll_number": s["roll_number"], "pings": ping_count}
        
        if ping_count == 0:
            absent_list.append(student_data)
        elif ping_count >= threshold:
            present_list.append(student_data)
        else:
            suspicious_list.append(student_data)
            
    return {
        "session": dict(session),
        "present": present_list,
        "suspicious": suspicious_list,
        "absent": absent_list
    }
