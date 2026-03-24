import datetime
from .face_engine import FaceEngine

engine = FaceEngine()

def register_user(db, role: str, name: str, id_number: str, email: str, password_hash: str, front_image: str, left_image: str, right_image: str) -> dict:
    """
    Registers a new student or lecturer, extracts face embeddings from 3 angles, and stores them in SQLite.
    """
    cursor = db.cursor()
    table = "lecturers" if role.lower() == "lecturer" else "students"
    id_col = "lecturer_id" if role.lower() == "lecturer" else "roll_number"

    # Check if user already exists
    cursor.execute(f"SELECT id FROM {table} WHERE {id_col}=? OR email=?", (id_number, email))
    if cursor.fetchone():
        raise ValueError(f"{role.capitalize()} with this ID or email already exists.")
        
    try:
        if role.lower() == "lecturer":
            cursor.execute("INSERT INTO lecturers (name, lecturer_id, email, password_hash) VALUES (?, ?, ?, ?)",
                           (name, id_number, email, password_hash))
            db.commit()
            return {"_id": cursor.lastrowid}

        # Extract encodings robustly
        encodings = []
        for img_data in [front_image, left_image, right_image]:
            if not img_data:
                continue
            try:
                enc = engine.get_face_embedding(img_data)
                encodings.append(enc)
            except ValueError:
                pass
                
        if len(encodings) == 0:
            raise ValueError("No face detected in any of the provided images. Please ensure your face is clearly visible and well-lit.")
            
        avg_enc = [sum(col) / len(col) for col in zip(*encodings)]
    except Exception as e:
        raise ValueError(f"Failed to process registration: {str(e)}")

    import json
    enc_str = json.dumps(avg_enc)

    cursor.execute("INSERT INTO students (name, roll_number, email, password_hash, face_encoding, is_registered) VALUES (?, ?, ?, ?, ?, ?)",
                   (name, id_number, email, password_hash, enc_str, 1))

    db.commit()
    inserted_id = cursor.lastrowid
    return {"_id": inserted_id}

def verify_and_mark_attendance(db, student_id: str, target_lecturer_id: str, captured_image: str) -> dict:
    """
    Verifies Face, then silently marks attendance for the active class session of the targeted lecturer.
    """
    import json
    cursor = db.cursor()
    
    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # 0. Find Active Session for the targeted lecturer explicitly
    cursor.execute("""
        SELECT id FROM class_sessions 
        WHERE lecturer_id = (SELECT id FROM lecturers WHERE lecturer_id=?)
        AND date=? AND ? >= start_time AND ? <= end_time
    """, (target_lecturer_id, today_str, time_str, time_str))
    session = cursor.fetchone()

    if not session:
        raise ValueError(f"No active class session currently running for Lecturer {target_lecturer_id}.")

    session_id = session["id"]

    cursor.execute("SELECT * FROM students WHERE id=?", (student_id,))
    student = cursor.fetchone()
    
    if not student:
        raise ValueError("Student not found.")
        
    if not student["face_encoding"]:
        raise ValueError("Student face not registered.")

    # 1. Face Verification
    try:
        captured_enc = engine.get_face_embedding(captured_image)
    except Exception as e:
        raise ValueError(f"Face verification failed: {str(e)}")

    stored_enc = json.loads(student["face_encoding"])
    if not engine.compare_faces(stored_enc, captured_enc):
        raise PermissionError("Face verification failed: The captured face does not match the registered student.")
        
    # 2. Mark Attendance Ping
    cursor.execute("SELECT id, ping_count FROM attendance_records WHERE student_id=? AND session_id=?", (student_id, session_id))
    existing_record = cursor.fetchone()
    
    if existing_record:
        # Increment ping
        new_ping = existing_record["ping_count"] + 1
        cursor.execute("UPDATE attendance_records SET ping_count=? WHERE id=?", (new_ping, existing_record["id"]))
        db.commit()
        return {"status": "success", "message": f"Ping incremented to {new_ping}."}
        
    cursor.execute("INSERT INTO attendance_records (session_id, student_id, ping_count, first_seen_time, captured_image_path) VALUES (?, ?, ?, ?, ?)",
                   (session_id, student_id, 1, time_str, None))
    db.commit()
    inserted_id = cursor.lastrowid
    
    return {"status": "success", "message": "First presence registered.", "_id": inserted_id}

def periodic_presence_check(db, student_id: str, target_lecturer_id: str, captured_image: str):
    """
    Silent verification logic for periodic background checks.
    """
    try:
        res = verify_and_mark_attendance(db, student_id, target_lecturer_id, captured_image)
        return {"status": "success", "message": res["message"]}
    except Exception as e:
        return {"status": "failed", "reason": str(e)}
