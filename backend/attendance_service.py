import datetime
from .pipeline_config import get_face_engine, PipelineConfig

# Lazy engine initialization — don't instantiate at import time
_engine = None

def _get_engine():
    """Get or create the face engine instance (lazy singleton)."""
    global _engine
    if _engine is None:
        _engine = get_face_engine()
    return _engine


def register_user(db, role: str, name: str, id_number: str, email: str, password_hash: str, front_image: str, left_image: str, right_image: str) -> dict:
    """
    Registers a new student or lecturer, extracts face embeddings from 3 angles, and stores them in SQLite.
    """
    import json
    cursor = db.cursor()
    table = "lecturers" if role.lower() == "lecturer" else "students"
    id_col = "lecturer_id" if role.lower() == "lecturer" else "roll_number"

    # Check if user already exists
    cursor.execute(f"SELECT id FROM {table} WHERE {id_col}=? OR email=?", (id_number, email))
    if cursor.fetchone():
        raise ValueError(f"{role.capitalize()} with this ID or email already exists.")

    # Handle lecturer registration
    if role.lower() == "lecturer":
        try:
            cursor.execute("INSERT INTO lecturers (name, lecturer_id, email, password_hash) VALUES (?, ?, ?, ?)",
                           (name, id_number, email, password_hash))
            db.commit()
            return {"_id": cursor.lastrowid}
        except Exception as e:
            db.rollback()
            raise ValueError(f"Failed to register lecturer: {str(e)}")

    # Handle student registration — extract face encodings
    engine = _get_engine()
    encodings = []
    encoding_errors = []

    for angle, img_data in [("front", front_image), ("left", left_image), ("right", right_image)]:
        if not img_data:
            encoding_errors.append(f"{angle.capitalize()} image not provided")
            continue
        try:
            enc = engine.get_face_embedding(img_data)
            encodings.append(enc)
        except ValueError as e:
            encoding_errors.append(f"{angle.capitalize()}: {str(e)}")
        except Exception as e:
            encoding_errors.append(f"{angle.capitalize()}: Unexpected error - {str(e)}")

    if len(encodings) == 0:
        error_details = " | ".join(encoding_errors) if encoding_errors else "Unknown error"
        raise ValueError(f"No face detected in any images. {error_details}")

    # Average the face encodings for robustness
    try:
        avg_enc = [float(sum(col) / len(col)) for col in zip(*encodings)]
    except Exception as e:
        raise ValueError(f"Failed to process face embeddings: {str(e)}")

    # Insert student into database
    try:
        enc_str = json.dumps(avg_enc)
        cursor.execute("INSERT INTO students (name, roll_number, email, password_hash, face_encoding, is_registered) VALUES (?, ?, ?, ?, ?, ?)",
                       (name, id_number, email, password_hash, enc_str, 1))
        db.commit()
        inserted_id = cursor.lastrowid
        return {"_id": inserted_id}
    except Exception as e:
        db.rollback()
        raise ValueError(f"Failed to save student record: {str(e)}")


def verify_and_mark_attendance(db, student_id: str, target_lecturer_id: str, captured_image: str) -> dict:
    """
    Verifies Face, then silently marks attendance for the active class session of the targeted lecturer.
    Supports both standard and advanced pipelines with confidence scoring.
    """
    import json
    engine = _get_engine()
    cursor = db.cursor()

    now = datetime.datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")

    # 0. Find Active Session — targeted or any
    if target_lecturer_id:
        cursor.execute("""
            SELECT id, class_name, class_id FROM class_sessions
            WHERE lecturer_id = (SELECT id FROM lecturers WHERE lecturer_id=?)
            AND date=? AND ? >= start_time AND ? <= end_time
        """, (target_lecturer_id, today_str, time_str, time_str))
    else:
        cursor.execute("""
            SELECT id, class_name, class_id FROM class_sessions
            WHERE date=? AND ? >= start_time AND ? <= end_time
        """, (today_str, time_str, time_str))
    session = cursor.fetchone()

    if not session:
        msg = "No active class session currently running"
        if target_lecturer_id:
            msg += f" for Lecturer {target_lecturer_id}"
        raise ValueError(msg + ".")

    session_id = session["id"]
    class_name = session["class_name"]
    class_id = session["class_id"]

    cursor.execute("SELECT * FROM students WHERE id=?", (student_id,))
    student = cursor.fetchone()

    if not student:
        raise ValueError("Student not found.")

    if not student["face_encoding"]:
        raise ValueError("Student face not registered.")

    # 1. Liveness Detection (if enabled)
    if PipelineConfig.ENABLE_LIVENESS:
        try:
            if PipelineConfig.is_advanced():
                liveness_result = engine.check_liveness_advanced(captured_image)
                is_live = liveness_result.get("is_live", False)
            else:
                is_live = engine.check_liveness(captured_image)

            if not is_live:
                raise PermissionError("Liveness check failed: Image may be a photo or video.")
        except PermissionError:
            raise
        except Exception as e:
            raise ValueError(f"Liveness detection error: {str(e)}")

    # 2. Face Verification
    try:
        if PipelineConfig.is_advanced():
            captured_result = engine.get_face_embedding(captured_image)
            captured_enc = captured_result["embedding"]
        else:
            captured_enc = engine.get_face_embedding(captured_image)
    except Exception as e:
        raise ValueError(f"Face verification failed: {str(e)}")

    stored_enc = json.loads(student["face_encoding"])

    # 3. Compare faces based on pipeline type
    if PipelineConfig.is_advanced():
        comparison = engine.compare_faces_cosine(stored_enc, captured_enc)
        is_match = comparison["match"]
        confidence = comparison["confidence"]
        match_info = {
            "similarity": comparison["cosine_similarity"],
            "distance": comparison["distance"],
            "confidence_pct": confidence
        }
    else:
        is_match = engine.compare_faces(stored_enc, captured_enc)
        confidence = 100.0 if is_match else 0.0
        match_info = {"confidence_pct": confidence}

    if not is_match:
        raise PermissionError(f"Face verification failed: The captured face does not match the registered student. (Confidence: {confidence:.1f}%)")

    # 4. Mark Attendance Record
    cursor.execute("SELECT id, ping_count FROM attendance_records WHERE student_id=? AND session_id=?", (student_id, session_id))
    existing_record = cursor.fetchone()

    if existing_record:
        new_ping = existing_record["ping_count"] + 1
        cursor.execute("UPDATE attendance_records SET ping_count=? WHERE id=?", (new_ping, existing_record["id"]))
        db.commit()
        return {
            "status": "success",
            "message": f"Ping incremented to {new_ping}.",
            "match_info": match_info,
            "confidence": confidence,
            "class_name": class_name,
            "class_id": class_id,
            "session_id": session_id
        }

    # Create new attendance record
    cursor.execute("INSERT INTO attendance_records (session_id, student_id, ping_count, first_seen_time, captured_image_path) VALUES (?, ?, ?, ?, ?)",
                   (session_id, student_id, 1, time_str, None))
    db.commit()
    inserted_id = cursor.lastrowid

    return {
        "status": "success",
        "message": "First presence registered.",
        "_id": inserted_id,
        "match_info": match_info,
        "confidence": confidence,
        "class_name": class_name,
        "class_id": class_id,
        "session_id": session_id
    }


def periodic_presence_check(db, student_id: str, target_lecturer_id: str, captured_image: str):
    """
    Silent verification logic for periodic background checks.
    """
    try:
        res = verify_and_mark_attendance(db, student_id, target_lecturer_id, captured_image)
        return {"status": "success", "message": res["message"]}
    except Exception as e:
        return {"status": "failed", "reason": str(e)}
