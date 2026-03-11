from sqlalchemy import create_engine, Column, Integer, String, Boolean, Date, Time, ForeignKey, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

# SQLite is used for local development out-of-the-box.
# Change string to "postgresql://user:password@localhost/dbname" for PostgreSQL
SQLALCHEMY_DATABASE_URL = "sqlite:///./attendance.db"

# Setting check_same_thread to False is required for SQLite and FastAPI
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    course_code = Column(String(50), unique=True, index=True)
    course_name = Column(String(255))

class Lecturer(Base):
    __tablename__ = "lecturers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    email = Column(String(255), unique=True, index=True)
    password_hash = Column(String(255))

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255))
    roll_number = Column(String(100), unique=True, index=True)
    email = Column(String(255), unique=True, index=True)
    password_hash = Column(String(255))
    face_encoding = Column(JSON, nullable=True) # Stores the 128-d numpy array as a JSON list
    is_registered = Column(Boolean, default=False)
    
    attendance_records = relationship("AttendanceRecord", back_populates="student")

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    date = Column(Date)
    time = Column(Time)
    status = Column(String(50)) # 'PRESENT', 'ABSENT'
    ip_address = Column(String(50))
    captured_image_path = Column(String(500), nullable=True)
    
    student = relationship("Student", back_populates="attendance_records")

class AllowedNetwork(Base):
    __tablename__ = "allowed_networks"
    id = Column(Integer, primary_key=True, index=True)
    network_cidr = Column(String(50)) # e.g., '192.168.1.0/24'
    description = Column(String(255))

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create all tables function
def init_db():
    Base.metadata.create_all(bind=engine)
