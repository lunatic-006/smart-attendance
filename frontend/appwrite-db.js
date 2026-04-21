/**
 * Appwrite Database Helper — Smart Attendance System
 * All CRUD operations for the attendance system using Appwrite SDK.
 * Replaces backend/main_api.py + backend/attendance_service.py
 * 
 * Depends on: appwrite-config.js (must be loaded first)
 */

// ==================== AUTH HELPERS ====================

/**
 * Register a new user (student or lecturer).
 * Creates an Appwrite Auth account + a document in the appropriate collection.
 */
async function registerUser({ role, name, idNumber, email, password, faceEncoding = null }) {
    // 1. Create Appwrite Auth account
    let authUser;
    try {
        authUser = await appwriteAccount.create(ID.unique(), email, password, name);
    } catch (err) {
        if (err.code === 409) {
            throw new Error(`A user with this email already exists.`);
        }
        throw new Error(`Failed to create account: ${err.message}`);
    }

    // 2. Create email session to authenticate for document creation
    try {
        await appwriteAccount.createEmailPasswordSession(email, password);
    } catch (err) {
        throw new Error(`Account created but login failed: ${err.message}`);
    }

    // 3. Create document in appropriate collection
    try {
        if (role === 'lecturer') {
            const doc = await appwriteDB.createDocument(
                DB_ID,
                COLLECTIONS.LECTURERS,
                ID.unique(),
                {
                    name: name,
                    lecturer_id: idNumber,
                    email: email,
                    auth_user_id: authUser.$id,
                }
            );
            return { docId: doc.$id, authUserId: authUser.$id };
        } else {
            // Student — include face encoding
            const doc = await appwriteDB.createDocument(
                DB_ID,
                COLLECTIONS.STUDENTS,
                ID.unique(),
                {
                    name: name,
                    roll_number: idNumber,
                    email: email,
                    auth_user_id: authUser.$id,
                    face_encoding: faceEncoding ? JSON.stringify(faceEncoding) : '',
                    is_registered: faceEncoding ? true : false,
                }
            );
            return { docId: doc.$id, authUserId: authUser.$id };
        }
    } catch (err) {
        // Clean up: delete the auth account if document creation fails
        try { await appwriteAccount.deleteSession('current'); } catch(_) {}
        throw new Error(`Failed to save profile: ${err.message}`);
    }
}

/**
 * Login a student by roll number + password.
 * Looks up email from students collection, then authenticates.
 */
async function loginStudent(rollNumber, password) {
    // 1. Find student by roll number
    const results = await appwriteDB.listDocuments(
        DB_ID,
        COLLECTIONS.STUDENTS,
        [Query.equal('roll_number', rollNumber), Query.limit(1)]
    );

    if (results.documents.length === 0) {
        throw new Error('Invalid credentials');
    }

    const studentDoc = results.documents[0];

    // 2. Authenticate with Appwrite Auth using email from the document
    try {
        // Delete any existing session first
        try { await appwriteAccount.deleteSession('current'); } catch(_) {}
        await appwriteAccount.createEmailPasswordSession(studentDoc.email, password);
    } catch (err) {
        throw new Error('Invalid credentials');
    }

    return {
        docId: studentDoc.$id,
        name: studentDoc.name,
        rollNumber: studentDoc.roll_number,
        faceEncoding: studentDoc.face_encoding,
    };
}

/**
 * Login a lecturer by lecturer_id + password.
 */
async function loginLecturer(lecturerId, password) {
    // 1. Find lecturer by lecturer_id
    const results = await appwriteDB.listDocuments(
        DB_ID,
        COLLECTIONS.LECTURERS,
        [Query.equal('lecturer_id', lecturerId), Query.limit(1)]
    );

    if (results.documents.length === 0) {
        throw new Error('Invalid lecturer credentials');
    }

    const lecturerDoc = results.documents[0];

    // 2. Authenticate
    try {
        try { await appwriteAccount.deleteSession('current'); } catch(_) {}
        await appwriteAccount.createEmailPasswordSession(lecturerDoc.email, password);
    } catch (err) {
        throw new Error('Invalid lecturer credentials');
    }

    return {
        docId: lecturerDoc.$id,
        lecturerId: lecturerDoc.lecturer_id,
        name: lecturerDoc.name,
    };
}

/**
 * Logout — destroy current session.
 */
async function logoutUser() {
    try {
        await appwriteAccount.deleteSession('current');
    } catch (_) {}
    localStorage.clear();
}

// ==================== CLASS SESSION HELPERS ====================

/**
 * Create a new class session.
 */
async function createClassSession({ lecturerDocId, lecturerCustomId, className, classId, date, startTime, durationMinutes }) {
    // Parse and validate
    const dateStr = date || new Date().toISOString().split('T')[0];
    const startTimeStr = startTime ? `${startTime}:00` : new Date().toTimeString().split(' ')[0];
    const duration = durationMinutes && durationMinutes > 0 ? durationMinutes : 60;

    // Calculate end time
    const startDt = new Date(`${dateStr}T${startTimeStr}`);
    const endDt = new Date(startDt.getTime() + duration * 60 * 1000);
    const endTimeStr = endDt.toTimeString().split(' ')[0];

    const doc = await appwriteDB.createDocument(
        DB_ID,
        COLLECTIONS.CLASS_SESSIONS,
        ID.unique(),
        {
            lecturer_id: lecturerDocId,
            lecturer_custom_id: lecturerCustomId,
            class_id: classId || '',
            class_name: className,
            date: dateStr,
            start_time: startTimeStr.substring(0, 8),
            end_time: endTimeStr.substring(0, 8),
            total_expected_pings: duration,
        }
    );

    return { sessionId: doc.$id };
}

/**
 * Get today's class sessions for a lecturer.
 */
async function getSessionsForLecturer(lecturerCustomId) {
    const todayStr = new Date().toISOString().split('T')[0];

    const results = await appwriteDB.listDocuments(
        DB_ID,
        COLLECTIONS.CLASS_SESSIONS,
        [
            Query.equal('lecturer_custom_id', lecturerCustomId),
            Query.equal('date', todayStr),
            Query.limit(50),
        ]
    );

    return results.documents;
}

/**
 * Delete a class session and its related attendance records.
 */
async function deleteClassSession(sessionDocId) {
    // 1. Delete all attendance records for this session
    const records = await appwriteDB.listDocuments(
        DB_ID,
        COLLECTIONS.ATTENDANCE_RECORDS,
        [Query.equal('session_id', sessionDocId), Query.limit(100)]
    );

    for (const record of records.documents) {
        await appwriteDB.deleteDocument(DB_ID, COLLECTIONS.ATTENDANCE_RECORDS, record.$id);
    }

    // 2. Delete the session itself
    await appwriteDB.deleteDocument(DB_ID, COLLECTIONS.CLASS_SESSIONS, sessionDocId);
}

// ==================== ATTENDANCE HELPERS ====================

/**
 * Find the currently active class session for a lecturer.
 */
async function findActiveSession(targetLecturerId) {
    const todayStr = new Date().toISOString().split('T')[0];
    const nowTime = new Date().toTimeString().split(' ')[0]; // HH:MM:SS

    let queries = [
        Query.equal('date', todayStr),
        Query.lessThanEqual('start_time', nowTime),
        Query.greaterThanEqual('end_time', nowTime),
        Query.limit(1),
    ];

    if (targetLecturerId) {
        queries.unshift(Query.equal('lecturer_custom_id', targetLecturerId));
    }

    const results = await appwriteDB.listDocuments(
        DB_ID,
        COLLECTIONS.CLASS_SESSIONS,
        queries
    );

    if (results.documents.length === 0) {
        let msg = 'No active class session currently running';
        if (targetLecturerId) msg += ` for Lecturer ${targetLecturerId}`;
        throw new Error(msg + '.');
    }

    return results.documents[0];
}

/**
 * Mark attendance — create or increment ping for a student in a session.
 */
async function markAttendance(sessionDocId, studentDocId) {
    // Check if record already exists
    const existing = await appwriteDB.listDocuments(
        DB_ID,
        COLLECTIONS.ATTENDANCE_RECORDS,
        [
            Query.equal('session_id', sessionDocId),
            Query.equal('student_id', studentDocId),
            Query.limit(1),
        ]
    );

    const nowTime = new Date().toTimeString().split(' ')[0];

    if (existing.documents.length > 0) {
        // Increment ping count
        const record = existing.documents[0];
        const newPing = (record.ping_count || 1) + 1;

        await appwriteDB.updateDocument(
            DB_ID,
            COLLECTIONS.ATTENDANCE_RECORDS,
            record.$id,
            { ping_count: newPing }
        );

        return { status: 'success', message: `Ping incremented to ${newPing}.`, pingCount: newPing };
    } else {
        // Create new record
        const doc = await appwriteDB.createDocument(
            DB_ID,
            COLLECTIONS.ATTENDANCE_RECORDS,
            ID.unique(),
            {
                session_id: sessionDocId,
                student_id: studentDocId,
                ping_count: 1,
                first_seen_time: nowTime,
            }
        );

        return { status: 'success', message: 'First presence registered.', pingCount: 1, recordId: doc.$id };
    }
}

/**
 * Get attendance report for a session (present, suspicious, absent lists).
 */
async function getSessionReport(sessionDocId) {
    // 1. Get the session details
    const session = await appwriteDB.getDocument(DB_ID, COLLECTIONS.CLASS_SESSIONS, sessionDocId);

    // 2. Calculate elapsed pings (for dynamic thresholds)
    const now = new Date();
    const sessionStart = new Date(`${session.date}T${session.start_time}`);
    let elapsedPings = 0;

    if (now >= sessionStart) {
        const elapsedMs = now - sessionStart;
        const elapsedMinutes = Math.floor(elapsedMs / 60000);
        elapsedPings = Math.min(elapsedMinutes, session.total_expected_pings);
    }

    const threshold = 0.8 * elapsedPings;

    // 3. Get all attendance records for this session
    const records = await appwriteDB.listDocuments(
        DB_ID,
        COLLECTIONS.ATTENDANCE_RECORDS,
        [Query.equal('session_id', sessionDocId), Query.limit(200)]
    );

    const recordMap = {};
    for (const r of records.documents) {
        recordMap[r.student_id] = r.ping_count;
    }

    // 4. Get all students
    const allStudents = await appwriteDB.listDocuments(
        DB_ID,
        COLLECTIONS.STUDENTS,
        [Query.limit(200)]
    );

    const present = [];
    const suspicious = [];
    const absent = [];

    for (const s of allStudents.documents) {
        const pingCount = recordMap[s.$id] || 0;
        const studentData = {
            id: s.$id,
            name: s.name,
            roll_number: s.roll_number,
            pings: pingCount,
        };

        if (pingCount === 0) {
            absent.push(studentData);
        } else if (pingCount >= threshold && pingCount > 0) {
            present.push(studentData);
        } else {
            suspicious.push(studentData);
        }
    }

    return { session, present, suspicious, absent };
}

console.log('📦 Appwrite DB helper loaded');
