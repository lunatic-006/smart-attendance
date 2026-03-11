-- Smart Face Recognition Attendance System Schema
-- Run this script to manually create tables in PostgreSQL/MySQL.
-- NOTE: If using SQLAlchemy's create_all(), this script is not strictly required but serves as a reference.

CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    course_code VARCHAR(50) UNIQUE NOT NULL,
    course_name VARCHAR(255) NOT NULL
);

CREATE TABLE lecturers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL
);

CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    roll_number VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    -- face_encoding vector can be stored as JSON, BYTEA, or array depending on the DB.
    -- We will store the 128-dimensional embedding as JSON for broader compatibility.
    face_encoding JSON,
    is_registered BOOLEAN DEFAULT FALSE
);

CREATE TABLE attendance_records (
    id SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    time TIME NOT NULL,
    status VARCHAR(50) NOT NULL, -- e.g., 'PRESENT', 'ABSENT'
    ip_address VARCHAR(50) NOT NULL,
    captured_image_path VARCHAR(500), -- path to internal storage if saving logs
    CONSTRAINT unique_attendance_per_day UNIQUE (student_id, date)
);

CREATE TABLE allowed_networks (
    id SERIAL PRIMARY KEY,
    network_cidr VARCHAR(50) NOT NULL, -- e.g., '192.168.1.0/24'
    description VARCHAR(255)
);

-- Insert default allowed network for local development loopback
INSERT INTO allowed_networks (network_cidr, description) VALUES ('127.0.0.0/8', 'Localhost Default');
