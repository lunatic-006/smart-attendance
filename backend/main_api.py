import io
import csv
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives.hashes import SHA256
import datetime

from .database import engine, Base, get_db, Student, AttendanceRecord, Lecturer, init_db
from .attendance_service import register_student, verify_and_mark_attendance, periodic_presence_check

app = FastAPI(title="Smart Face Recognition Attendance API")

# Setup CORS for Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic Schemas
class StudentRegistrationReq(BaseModel):
    name: str
    roll_number: str
    email: str
    passwordHash: str
    front_image: str
    left_image: str
    right_image: str

class AttendanceMarkReq(BaseModel):
    student_id: int
    captured_image: str

class PeriodicPingReq(BaseModel):
    student_id: int
    captured_image: str

@app.on_event("startup")
def on_startup():
    init_db()

@app.post("/api/register/student")
def api_register_student(req: StudentRegistrationReq, db: Session = Depends(get_db)):
    try:
        student = register_student(
            db=db, 
            name=req.name, 
            roll_number=req.roll_number, 
            email=req.email, 
            password_hash=req.passwordHash,
            front_image=req.front_image, 
            left_image=req.left_image, 
            right_image=req.right_image
        )
        return {"message": "Registration successful", "student_id": student.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/login/student")
def api_login_student(email: str, password_hash: str, db: Session = Depends(get_db)):
    """Simple login (MVP). Should use JWT in production."""
    student = db.query(Student).filter(Student.email == email, Student.password_hash == password_hash).first()
    if not student:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"message": "Login successful", "student_id": student.id, "name": student.name}

@app.post("/api/attendance/mark")
def api_mark_attendance(req: AttendanceMarkReq, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host
    try:
        record = verify_and_mark_attendance(
            db=db,
            student_id=req.student_id,
            client_ip=client_ip,
            captured_image=req.captured_image
        )
        return {"message": f"Attendance marked for IP {client_ip}", "status": record.status}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/attendance/ping")
def api_periodic_ping(req: PeriodicPingReq, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host
    result = periodic_presence_check(
        db=db,
        student_id=req.student_id,
        client_ip=client_ip,
        captured_image=req.captured_image
    )
    if result.get("status") == "failed":
        # Usually we wouldn't throw a full HTTP error for a silent check, 
        # but returning it gracefully lets the frontend know to warn the user.
        return JSONResponse(status_code=400, content=result)
    return result

# Lecturer Endpoints
@app.get("/api/dashboard/stats")
def api_dashboard_stats(db: Session = Depends(get_db)):
    """Provides data for Chart.js"""
    today = datetime.date.today()
    total_students = db.query(Student).count()
    present_today = db.query(AttendanceRecord).filter(AttendanceRecord.date == today).count()
    absent_today = total_students - present_today
    
    return {
        "labels": ["Present", "Absent"],
        "data": [present_today, absent_today]
    }

@app.get("/api/dashboard/export-csv")
def export_attendance_csv(db: Session = Depends(get_db)):
    """Exports all attendance records to a CSV file"""
    records = db.query(AttendanceRecord).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Student ID', 'Date', 'Time', 'Status', 'IP Address'])
    
    for r in records:
        writer.writerow([r.id, r.student_id, r.date, r.time, r.status, r.ip_address])
        
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance_export.csv"}
    )
