/**
 * Appwrite Collection Setup Script
 * Run this ONCE to create all required collections and attributes in your Appwrite database.
 * 
 * Prerequisites:
 *   1. npm install node-appwrite
 *   2. Create an API Key in Appwrite Console → Settings → API Keys
 *      (Grant permissions: databases.read, databases.write, collections.read, collections.write)
 *   3. Set your API key below or via APPWRITE_API_KEY env var
 * 
 * Usage:
 *   node setup-appwrite.mjs
 */

import { Client, Databases, ID, Permission, Role } from 'node-appwrite';

// ==================== Configuration ====================
const ENDPOINT = 'https://sgp.cloud.appwrite.io/v1';
const PROJECT_ID = '69e7a7be0028367e9cad';
const DATABASE_ID = '69e7a9db0018fe3d0f4e';
const API_KEY = process.env.APPWRITE_API_KEY || 'YOUR_API_KEY_HERE'; // <-- SET THIS

if (API_KEY === 'YOUR_API_KEY_HERE') {
    console.error('❌ Please set APPWRITE_API_KEY environment variable or edit this file.');
    console.error('   Create an API Key at: Appwrite Console → Settings → API Keys');
    console.error('   Usage: APPWRITE_API_KEY=your_key_here node setup-appwrite.mjs');
    process.exit(1);
}

// ==================== Initialize Client ====================
const client = new Client()
    .setEndpoint(ENDPOINT)
    .setProject(PROJECT_ID)
    .setKey(API_KEY);

const databases = new Databases(client);

// Permissions: allow any user to read (for login lookups), authenticated users to write
const defaultPermissions = [
    Permission.read(Role.any()),
    Permission.create(Role.users()),
    Permission.update(Role.users()),
    Permission.delete(Role.users()),
];

// ==================== Helper: Create collection with retry ====================
async function createCollection(collectionId, name) {
    try {
        await databases.createCollection(DATABASE_ID, collectionId, name, defaultPermissions);
        console.log(`  ✅ Collection created: ${name} (${collectionId})`);
    } catch (err) {
        if (err.code === 409) {
            console.log(`  ⚠️  Collection already exists: ${name} (${collectionId})`);
        } else {
            throw err;
        }
    }
}

async function createStringAttr(collectionId, key, size, required = true) {
    try {
        await databases.createStringAttribute(DATABASE_ID, collectionId, key, size, required);
        console.log(`    + String: ${key} (size: ${size})`);
    } catch (err) {
        if (err.code === 409) {
            console.log(`    ⚠️ Attribute exists: ${key}`);
        } else {
            console.error(`    ❌ Failed: ${key} — ${err.message}`);
        }
    }
}

async function createIntAttr(collectionId, key, required = true, defaultVal = null) {
    try {
        await databases.createIntegerAttribute(DATABASE_ID, collectionId, key, required, undefined, undefined, defaultVal);
        console.log(`    + Integer: ${key}`);
    } catch (err) {
        if (err.code === 409) {
            console.log(`    ⚠️ Attribute exists: ${key}`);
        } else {
            console.error(`    ❌ Failed: ${key} — ${err.message}`);
        }
    }
}

async function createBoolAttr(collectionId, key, required = false, defaultVal = false) {
    try {
        await databases.createBooleanAttribute(DATABASE_ID, collectionId, key, required, defaultVal);
        console.log(`    + Boolean: ${key}`);
    } catch (err) {
        if (err.code === 409) {
            console.log(`    ⚠️ Attribute exists: ${key}`);
        } else {
            console.error(`    ❌ Failed: ${key} — ${err.message}`);
        }
    }
}

async function createEmailAttr(collectionId, key, required = true) {
    try {
        await databases.createEmailAttribute(DATABASE_ID, collectionId, key, required);
        console.log(`    + Email: ${key}`);
    } catch (err) {
        if (err.code === 409) {
            console.log(`    ⚠️ Attribute exists: ${key}`);
        } else {
            console.error(`    ❌ Failed: ${key} — ${err.message}`);
        }
    }
}

async function createIndex(collectionId, key, type = 'key', attributes = [key]) {
    try {
        await databases.createIndex(DATABASE_ID, collectionId, `idx_${key}`, type, attributes);
        console.log(`    🔍 Index: idx_${key}`);
    } catch (err) {
        if (err.code === 409) {
            console.log(`    ⚠️ Index exists: idx_${key}`);
        } else {
            console.error(`    ❌ Index failed: idx_${key} — ${err.message}`);
        }
    }
}

// ==================== Setup All Collections ====================
async function setup() {
    console.log('🚀 Setting up Appwrite collections...\n');

    // ---------- 1. Lecturers ----------
    console.log('📋 Creating: lecturers');
    await createCollection('lecturers', 'Lecturers');
    await createStringAttr('lecturers', 'name', 255);
    await createStringAttr('lecturers', 'lecturer_id', 100);
    await createEmailAttr('lecturers', 'email');
    await createStringAttr('lecturers', 'auth_user_id', 255);
    // Wait for attributes to be ready before creating indexes
    await sleep(2000);
    await createIndex('lecturers', 'lecturer_id', 'unique', ['lecturer_id']);
    await createIndex('lecturers', 'email', 'unique', ['email']);

    // ---------- 2. Students ----------
    console.log('\n📋 Creating: students');
    await createCollection('students', 'Students');
    await createStringAttr('students', 'name', 255);
    await createStringAttr('students', 'roll_number', 100);
    await createEmailAttr('students', 'email');
    await createStringAttr('students', 'auth_user_id', 255);
    await createStringAttr('students', 'face_encoding', 1000000, false); // Large text for face descriptor JSON
    await createBoolAttr('students', 'is_registered', false, false);
    await sleep(3000);
    await createIndex('students', 'roll_number', 'unique', ['roll_number']);
    await createIndex('students', 'email', 'unique', ['email']);

    // ---------- 3. Class Sessions ----------
    console.log('\n📋 Creating: class_sessions');
    await createCollection('class_sessions', 'Class Sessions');
    await createStringAttr('class_sessions', 'lecturer_id', 255);
    await createStringAttr('class_sessions', 'lecturer_custom_id', 100);
    await createStringAttr('class_sessions', 'class_id', 100, false);
    await createStringAttr('class_sessions', 'class_name', 100);
    await createStringAttr('class_sessions', 'date', 10);
    await createStringAttr('class_sessions', 'start_time', 8);
    await createStringAttr('class_sessions', 'end_time', 8);
    await createIntAttr('class_sessions', 'total_expected_pings');
    await sleep(3000);
    await createIndex('class_sessions', 'lecturer_date', 'key', ['lecturer_custom_id', 'date']);
    await createIndex('class_sessions', 'date_time', 'key', ['date', 'start_time', 'end_time']);

    // ---------- 4. Attendance Records ----------
    console.log('\n📋 Creating: attendance_records');
    await createCollection('attendance_records', 'Attendance Records');
    await createStringAttr('attendance_records', 'session_id', 255);
    await createStringAttr('attendance_records', 'student_id', 255);
    await createIntAttr('attendance_records', 'ping_count', true, 1);
    await createStringAttr('attendance_records', 'first_seen_time', 8);
    await sleep(2000);
    await createIndex('attendance_records', 'session_id', 'key', ['session_id']);
    await createIndex('attendance_records', 'student_session', 'unique', ['student_id', 'session_id']);

    console.log('\n✅ All collections and attributes created successfully!');
    console.log('   You can now deploy your frontend to Vercel.');
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

setup().catch(err => {
    console.error('\n❌ Setup failed:', err.message);
    process.exit(1);
});
