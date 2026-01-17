import sqlite3
import os
from werkzeug.security import generate_password_hash

# -------------------------
# DATABASE PATH
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tutor.db")

# -------------------------
# GET DATABASE CONNECTION
# -------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows act like dicts
    return conn

# -------------------------
# INITIALIZE DATABASE
# -------------------------
def init_db():
    conn = get_db()
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            department TEXT,
            level TEXT,
            role TEXT DEFAULT 'student',
            is_suspended INTEGER DEFAULT 0
        )
    """)

    # Courses table
    c.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT UNIQUE NOT NULL,
            course_title TEXT NOT NULL,
            description TEXT
        )
    """)

    # Materials table
    c.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    # Payments table
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'unpaid',
            paid_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # -------------------------
    # SEED COURSES & MATERIALS
    # -------------------------
    courses = [
        ("Psy432", "Adolescent Psychology", "Adolescent development", ["lesson1.mp3", "lesson1.pdf"]),
        ("Psy409", "Biological Psychology", "Neural processes", ["lesson2.mp3", "lesson2.pdf"])
    ]

    for code, title, desc, files in courses:
        c.execute("SELECT id FROM courses WHERE course_code=?", (code,))
        if not c.fetchone():
            c.execute("INSERT INTO courses (course_code, course_title, description) VALUES (?, ?, ?)",
                      (code, title, desc))
            course_id = c.lastrowid
            # Add materials
            for f in files:
                file_type = "audio" if f.endswith(".mp3") else "pdf"
                c.execute("INSERT INTO materials (course_id, filename, file_type) VALUES (?, ?, ?)",
                          (course_id, f, file_type))

    # -------------------------
    # CREATE DEMO USER
    # -------------------------
    demo_email = "demo@widemind.test"
    demo_password = "demopassword"

    c.execute("SELECT id FROM users WHERE email=?", (demo_email,))
    if not c.fetchone():
        hashed_pw = generate_password_hash(demo_password)
        c.execute(
            "INSERT INTO users (name, email, password, department, level, role, is_suspended) VALUES (?, ?, ?, ?, ?, 'student', 0)",
            ("Admin Wide", demo_email, hashed_pw, "Psychology", "400")
        )
        demo_user_id = c.lastrowid

        c.execute(
            "INSERT INTO payments (user_id, amount, status) VALUES (?, ?, ?)",
            (demo_user_id, 20000, "paid")
        )

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully.")

def is_admin(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user and user["role"] == "admin"

# -------------------------
# HASH PASSWORD UTILITY
# -------------------------
def hash_password(password):
    return generate_password_hash(password)

# -------------------------
# RUN INIT
# -------------------------
if __name__ == "__main__":
    init_db()