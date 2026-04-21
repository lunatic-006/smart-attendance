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
    Safe to run multiple times — uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS.
    """
    # Ensure database folder exists
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Enable WAL journal mode for better concurrent read performance
    cursor.execute("PRAGMA journal_mode=WAL")
    
    # Always run the schema script — it uses IF NOT EXISTS so it's safe
    # This ensures new indexes and tables are created on existing databases
    if os.path.exists(SCHEMA_FILE):
        print(f"Applying schema from {SCHEMA_FILE}...")
        with open(SCHEMA_FILE, "r") as f:
            schema_script = f.read()
        conn.executescript(schema_script)
        print("Database schema applied successfully.")
    else:
        print(f"Warning: Schema script not found at {SCHEMA_FILE}")
            
    conn.commit()
    conn.close()
