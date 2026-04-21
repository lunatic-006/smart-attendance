/**
 * Appwrite Configuration - Smart Attendance System
 * Initializes Appwrite Client, Account, and Databases services.
 */

// ==================== Appwrite Credentials ====================
const APPWRITE_CONFIG = {
    ENDPOINT: 'https://sgp.cloud.appwrite.io/v1',
    PROJECT_ID: '69e7a7be0028367e9cad',
    DATABASE_ID: '69e7a9db0018fe3d0f4e',
};

// ==================== Collection IDs ====================
// These must match the collections created in Appwrite Console
const COLLECTIONS = {
    LECTURERS: 'lecturers',
    STUDENTS: 'students',
    CLASS_SESSIONS: 'class_sessions',
    ATTENDANCE_RECORDS: 'attendance_records',
};

// ==================== Initialize Appwrite SDK ====================
const { Client, Account, Databases, ID, Query } = Appwrite;

const appwriteClient = new Client()
    .setEndpoint(APPWRITE_CONFIG.ENDPOINT)
    .setProject(APPWRITE_CONFIG.PROJECT_ID);

const appwriteAccount = new Account(appwriteClient);
const appwriteDB = new Databases(appwriteClient);

// ==================== Helper Constants ====================
const DB_ID = APPWRITE_CONFIG.DATABASE_ID;

console.log('✅ Appwrite SDK initialized:', APPWRITE_CONFIG.ENDPOINT);
