import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_FILE = os.path.join(BASE_DIR, "database", "smart_attendance.db")
SCHEMA_FILE = os.path.join(BASE_DIR, "database", "schema.sql")

def get_db():
    """
    FastAPI dependency to get a raw SQLite database connection per request.
    Yields the connection and ensures it is closed after the request is finished.
    """
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    # Enable dictionary-like access to rows
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """
    Initializes database schema from schema.sql.
    Runs once on startup.
    """
    # Ensure database folder exists
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Check if a critical table like 'students' already exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='students'")
    if not cursor.fetchone():
        print(f"Initializing new SQLite database at {DB_FILE} using schema...")
        if os.path.exists(SCHEMA_FILE):
            with open(SCHEMA_FILE, "r") as f:
                schema_script = f.read()
            conn.executescript(schema_script)
            print("Database initialized successfully.")
        else:
            print(f"Error: Schema script not found at {SCHEMA_FILE}")
            
    conn.commit()
    conn.close()
