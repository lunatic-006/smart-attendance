import io
import csv
import os
import time
import datetime
import sqlite3
import asyncio
from collections import defaultdict
from fastapi import FastAPI, Depends, HTTPException, status, Request, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, field_validator

from .database import get_db, init_db
from .attendance_service import register_user, verify_and_mark_attendance, periodic_presence_check
from .pipeline_config import PipelineConfig, get_face_engine
from .password_utils import hash_password, verify_password

app = FastAPI(title="Smart Face Recognition Attendance API")

# ==================== SECURITY: Rate Limiting ====================
class RateLimiter:
    """Simple in-memory rate limiter for login endpoints."""
    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts = defaultdict(list)

    def is_rate_limited(self, key: str) -> bool:
        now = time.time()
        # Clean old entries
        self._attempts[key] = [t for t in self._attempts[key] if now - t < self.window_seconds]
        if len(self._attempts[key]) >= self.max_attempts:
            return True
        self._attempts[key].append(now)
        return False

    def reset(self, key: str):
        self._attempts.pop(key, None)

login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=60)

# ==================== CORS Configuration ====================
# Allow all origins for development flexibility (file://, Live Server, etc.)
# In production, set ALLOWED_ORIGINS env var to restrict
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*")
if ALLOWED_ORIGINS == "*":
    _cors_origins = ["*"]
else:
    _cors_origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ==================== HTML Escaping Utility ====================
def escape_html(text: str) -> str:
    """Escape HTML entities to prevent XSS."""
    if not isinstance(text, str):
        text = str(text)
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))

# ==================== Pydantic Schemas with Validation ====================
class UserRegistrationReq(BaseModel):
    role: str
    name: str
    id_number: str
    email: str
    password: str  # Accept plain password, hash server-side
    front_image: str = ""
    left_image: str = ""
    right_image: str = ""

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v.lower() not in ("student", "lecturer"):
            raise ValueError("Role must be 'student' or 'lecturer'")
        return v.lower()

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or len(v.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(v) > 255:
            raise ValueError("Name must be at most 255 characters")
        return v.strip()

    @field_validator("id_number")
    @classmethod
    def validate_id_number(cls, v):
        if not v or len(v.strip()) < 1:
            raise ValueError("ID number is required")
        if len(v) > 100:
            raise ValueError("ID number must be at most 100 characters")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not v or "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not v or len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

class StudentLoginReq(BaseModel):
    roll_number: str
    password: str

class LecturerLoginReq(BaseModel):
    lecturer_id: str
    password: str

class AttendanceMarkReq(BaseModel):
    student_id: str
    target_lecturer_id: str = ''
    captured_image: str

class PeriodicPingReq(BaseModel):
    student_id: str
    target_lecturer_id: str = ''
    captured_image: str

from typing import Optional

class SeedClassReq(BaseModel):
    lecturer_id: str  # The lecturer's custom ID (string, e.g. "L101" or "admin")
    class_name: str
    class_id: Optional[str] = None
    date: Optional[str] = None
    start_time: Optional[str] = None
    duration_minutes: Optional[int] = 60

# ==================== Static Files ====================
# Serve frontend files at /frontend/
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/frontend", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

# ==================== Startup ====================
@app.on_event("startup")
def on_startup():
    init_db()

# ==================== Pipeline Info Endpoints ====================
@app.get("/api/pipeline/info")
def api_pipeline_info():
    """Get current face recognition pipeline information."""
    try:
        engine = get_face_engine()
        pipeline_info = PipelineConfig.get_pipeline_info()

        if hasattr(engine, 'get_model_info'):
            model_info = engine.get_model_info()
            pipeline_info.update(model_info)

        return {"status": "success", "pipeline": pipeline_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline info: {escape_html(str(e))}")

@app.post("/api/pipeline/test-face-detection")
def api_test_face_detection(base64_image: str = Query(...)):
    """Test face detection on an image using current pipeline."""
    try:
        engine = get_face_engine()

        if PipelineConfig.is_advanced():
            detections = engine.detect_faces(base64_image)
            return {"status": "success", "detections": detections, "face_count": len(detections)}
        else:
            is_live = engine.check_liveness(base64_image)
            return {"status": "success", "liveness_detected": is_live, "pipeline_type": "standard"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "failed", "error": escape_html(str(e))})

@app.post("/api/pipeline/test-face-embedding")
def api_test_face_embedding(base64_image: str = Query(...)):
    """Test face embedding extraction using current pipeline."""
    try:
        engine = get_face_engine()

        if PipelineConfig.is_advanced():
            result = engine.get_face_embedding(base64_image)
            return {
                "status": "success",
                "embedding_dim": result["embedding_dim"],
                "confidence": result["confidence"],
                "bbox": result["bbox"],
                "embedding_sample": result["embedding"][:10]
            }
        else:
            embedding = engine.get_face_embedding(base64_image)
            return {"status": "success", "embedding_dim": len(embedding), "embedding_sample": embedding[:10]}
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "failed", "error": escape_html(str(e))})

# ==================== Registration ====================
@app.post("/api/register")
def register_endpoint(req: UserRegistrationReq, db=Depends(get_db)):
    try:
        # Hash the password server-side using bcrypt
        hashed_pw = hash_password(req.password)

        user = register_user(
            db=db,
            role=req.role,
            name=req.name,
            id_number=req.id_number,
            email=req.email,
            password_hash=hashed_pw,
            front_image=req.front_image,
            left_image=req.left_image,
            right_image=req.right_image
        )
        return {"message": "Registration successful", "user_id": user.get("_id", "unknown")}
    except Exception as e:
        raise HTTPException(status_code=400, detail=escape_html(str(e)))

# ==================== Login Endpoints (POST body, rate-limited) ====================
def _check_password(plain_password: str, stored_hash: str, db=None, table=None, user_id=None) -> bool:
    """
    Verify password — supports both bcrypt hashes and legacy plaintext.
    If a legacy plaintext match is found, auto-upgrades to bcrypt.
    """
    # Try bcrypt first (new format)
    if stored_hash and stored_hash.startswith("$2"):
        try:
            return verify_password(plain_password, stored_hash)
        except Exception:
            return False
    
    # Fallback: legacy plaintext comparison
    if stored_hash == plain_password:
        # Auto-upgrade to bcrypt if possible
        if db and table and user_id:
            try:
                new_hash = hash_password(plain_password)
                cursor = db.cursor()
                cursor.execute(f"UPDATE {table} SET password_hash=? WHERE id=?", (new_hash, user_id))
                db.commit()
            except Exception:
                pass  # Non-critical — upgrade silently
        return True
    
    return False

@app.post("/api/login/student")
def api_login_student(req: StudentLoginReq, request: Request, db=Depends(get_db)):
    # Rate limiting by client IP
    client_ip = request.client.host if request.client else "unknown"
    if login_rate_limiter.is_rate_limited(f"student_{client_ip}"):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please wait 60 seconds.")

    cursor = db.cursor()
    cursor.execute("SELECT * FROM students WHERE roll_number=?", (req.roll_number,))
    student = cursor.fetchone()

    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password (supports both bcrypt and legacy plaintext)
    if not _check_password(req.password, student["password_hash"], db=db, table="students", user_id=student["id"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    login_rate_limiter.reset(f"student_{client_ip}")
    return {"message": "Login successful", "student_id": str(student["id"]), "name": student["name"]}

@app.post("/api/login/lecturer")
def api_login_lecturer(req: LecturerLoginReq, request: Request, db=Depends(get_db)):
    # Rate limiting by client IP
    client_ip = request.client.host if request.client else "unknown"
    if login_rate_limiter.is_rate_limited(f"lecturer_{client_ip}"):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please wait 60 seconds.")

    cursor = db.cursor()
    cursor.execute("SELECT * FROM lecturers WHERE lecturer_id=? OR email=?", (req.lecturer_id, req.lecturer_id))
    lecturer = cursor.fetchone()

    if not lecturer:
        raise HTTPException(status_code=401, detail="Invalid lecturer credentials")

    # Verify password (supports both bcrypt and legacy plaintext)
    if not _check_password(req.password, lecturer["password_hash"], db=db, table="lecturers", user_id=lecturer["id"]):
        raise HTTPException(status_code=401, detail="Invalid lecturer credentials")

    login_rate_limiter.reset(f"lecturer_{client_ip}")
    return {"message": "Login successful", "lecturer_id": str(lecturer["lecturer_id"]), "name": lecturer["name"]}

# ==================== Attendance ====================
@app.post("/api/attendance/mark")
def api_mark_attendance(req: AttendanceMarkReq, db=Depends(get_db)):
    try:
        record = verify_and_mark_attendance(
            db=db,
            student_id=req.student_id,
            target_lecturer_id=req.target_lecturer_id,
            captured_image=req.captured_image
        )
        return {"message": "Attendance actively processed.", "status": record["status"]}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=escape_html(str(e)))
    except Exception as e:
        raise HTTPException(status_code=400, detail=escape_html(str(e)))

@app.post("/api/attendance/ping")
def api_periodic_ping(req: PeriodicPingReq, db=Depends(get_db)):
    result = periodic_presence_check(
        db=db,
        student_id=req.student_id,
        target_lecturer_id=req.target_lecturer_id,
        captured_image=req.captured_image
    )
    if result.get("status") == "failed":
        return JSONResponse(status_code=400, content=result)
    return result

# ==================== Lecturer Endpoints ====================
@app.post("/api/dev/seed-class")
def api_seed_class(req: SeedClassReq, db=Depends(get_db)):
    """Creates a class session with customizable date, start time, and duration."""
    cursor = db.cursor()
    now = datetime.datetime.now()

    # Validate and parse date
    if req.date:
        try:
            # Handle potential ISO formats or timestamps
            raw_date = req.date.split('T')[0]
            date_obj = datetime.datetime.strptime(raw_date, "%Y-%m-%d")
            date_str = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    else:
        date_str = now.strftime("%Y-%m-%d")

    # Validate and parse start time
    if req.start_time:
        try:
            # Extract HH:MM safely regardless of trailing seconds or milliseconds
            raw_time = req.start_time[:5]
            time_obj = datetime.datetime.strptime(raw_time, "%H:%M")
            start_time_str = time_obj.strftime("%H:%M:%S")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid time format. Use HH:MM")
    else:
        start_time_str = now.strftime("%H:%M:%S")

    # Determine duration
    duration = req.duration_minutes if req.duration_minutes is not None and req.duration_minutes > 0 else 60

    # Calculate end time
    start_datetime = datetime.datetime.strptime(f"{date_str} {start_time_str}", "%Y-%m-%d %H:%M:%S")
    end_datetime = start_datetime + datetime.timedelta(minutes=duration)
    end_time_str = end_datetime.strftime("%H:%M:%S")

    expected_pings = duration

    # Get lecturer database ID
    cursor.execute("SELECT id FROM lecturers WHERE lecturer_id=?", (str(req.lecturer_id),))
    lecturer = cursor.fetchone()
    if not lecturer:
        raise HTTPException(status_code=404, detail=f"Lecturer not found with ID: {escape_html(str(req.lecturer_id))}")

    lecturer_db_id = lecturer[0]

    cursor.execute("""
        INSERT INTO class_sessions (lecturer_id, class_id, class_name, date, start_time, end_time, total_expected_pings)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (lecturer_db_id, req.class_id, req.class_name, date_str, start_time_str, end_time_str, expected_pings))
    db.commit()

    return {"message": "Class session created successfully.", "session_id": cursor.lastrowid}

@app.get("/api/lecturer/sessions")
def api_get_sessions(lecturer_id: str = Query(...), db=Depends(get_db)):
    """Fetches today's classes for the lecturer."""
    cursor = db.cursor()
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    cursor.execute("SELECT id FROM lecturers WHERE lecturer_id=?", (lecturer_id,))
    lecturer = cursor.fetchone()
    if not lecturer:
        raise HTTPException(status_code=404, detail="Lecturer not found")

    lecturer_db_id = lecturer[0]

    cursor.execute("SELECT * FROM class_sessions WHERE lecturer_id=? AND date=?", (lecturer_db_id, today_str))
    sessions = cursor.fetchall()
    return {"sessions": [dict(s) for s in sessions]}

@app.get("/api/lecturer/session/{session_id}/report")
def api_get_session_report(session_id: int, db=Depends(get_db)):
    """Returns Present, Suspicious, Absent lists based on dynamic elapsed time thresholds."""
    cursor = db.cursor()

    cursor.execute("SELECT * FROM class_sessions WHERE id=?", (session_id,))
    session = cursor.fetchone()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    # Calculate expected pings based on elapsed time vs total time
    now = datetime.datetime.now()
    session_start_str = f'{session["date"]} {session["start_time"]}'
    session_start = datetime.datetime.strptime(session_start_str, "%Y-%m-%d %H:%M:%S")
    
    if now < session_start:
        elapsed_pings = 0
    else:
        elapsed_delta = now - session_start
        elapsed_minutes = int(elapsed_delta.total_seconds() // 60)
        # Cap expected_pings to total_expected_pings (duration)
        elapsed_pings = min(elapsed_minutes, float(session["total_expected_pings"]))

    threshold = 0.8 * elapsed_pings if elapsed_pings > 0 else 0

    cursor.execute("SELECT id, name, roll_number FROM students")
    all_students = cursor.fetchall()

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
        elif ping_count >= threshold and ping_count > 0:
            present_list.append(student_data)
        else:
            suspicious_list.append(student_data)

    return {
        "session": dict(session),
        "present": present_list,
        "suspicious": suspicious_list,
        "absent": absent_list
    }

@app.delete("/api/lecturer/session/{session_id}")
def api_delete_session(session_id: int, db=Depends(get_db)):
    """Deletes a class session and all its attendance records."""
    try:
        cursor = db.cursor()

        # Verify session exists first
        cursor.execute("SELECT id FROM class_sessions WHERE id=?", (session_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Class session not found.")

        # Delete attendance records first (foreign key dependency)
        cursor.execute("DELETE FROM attendance_records WHERE session_id=?", (session_id,))

        # Then delete the session
        cursor.execute("DELETE FROM class_sessions WHERE id=?", (session_id,))

        db.commit()
        return {"message": "Class session deleted successfully."}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=escape_html(str(e)))
