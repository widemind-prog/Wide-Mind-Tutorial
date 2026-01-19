print(">>> db.py imported")

import sqlite3
import os
from werkzeug.security import generate_password_hash
import logging
from datetime import datetime

# -------------------------
# DATABASE PATH
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tutor.db")

# -------------------------
# LOGGER FOR FK/INTEGRITY
# -------------------------
logging.basicConfig(
    filename=os.path.join(BASE_DIR, "db_fk.log"),
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# -------------------------
# GET DATABASE CONNECTION
# -------------------------
def get_db():
    """
    Returns a sqlite3 connection with foreign keys enforced.
    Rows act like dicts.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

# -------------------------
# FK-SAFE EXECUTION HELPER
# -------------------------
def execute_with_fk_logging(cursor, query, params=()):
    """
    Executes a query and logs FK/Integrity errors.
    """
    try:
        cursor.execute(query, params)
    except sqlite3.IntegrityError as e:
        logging.warning(f"FK/Integrity violation on query: {query} | params: {params} | Error: {e}")
        raise

# -------------------------
# INITIALIZE DATABASE
# -------------------------
def init_db():
    conn = get_db()
    c = conn.cursor()

    # -------------------------
    # USERS TABLE
    # -------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            department TEXT,
            level TEXT,
            role TEXT DEFAULT 'student',
            is_suspended INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -------------------------
    # COURSES TABLE
    # -------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT UNIQUE NOT NULL,
            course_title TEXT NOT NULL,
            description TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -------------------------
    # MATERIALS TABLE
    # -------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            title TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
    """)

    # -------------------------
    # PAYMENTS TABLE
    # -------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'unpaid',
            reference TEXT,
            paid_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # -------------------------
    # INDEXES
    # -------------------------
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(course_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_materials_course_id ON materials(course_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)")

    # -------------------------
    # SEED COURSES & MATERIALS
    # -------------------------
    courses = [
        ("Psy432", "Adolescent Psychology", "Adolescent development", [("lesson1.mp3", "Adolescent Audio Lesson 1"), ("lesson1.pdf", "Adolescent PDF Lesson 1")]),
        ("Psy409", "Biological Psychology", "Neural processes", [("lesson2.mp3", "Biology Audio Lesson 2"), ("lesson2.pdf", "Biology PDF Lesson 2")])
    ]

    for code, title, desc, files in courses:
        c.execute("SELECT id FROM courses WHERE course_code=?", (code,))
        if not c.fetchone():
            execute_with_fk_logging(c, "INSERT INTO courses (course_code, course_title, description) VALUES (?, ?, ?)", (code, title, desc))
            course_id = c.lastrowid
            for f, f_title in files:
                file_type = "audio" if f.endswith(".mp3") else "pdf"
                execute_with_fk_logging(c, "INSERT INTO materials (course_id, filename, file_type, title) VALUES (?, ?, ?, ?)", (course_id, f, file_type, f_title))

    # -------------------------
    # CREATE DEMO STUDENT USER
    # -------------------------
    demo_email = "demo@widemind.test"
    demo_password = "demopassword"
    c.execute("SELECT id FROM users WHERE email=?", (demo_email,))
    if not c.fetchone():
        hashed_pw = generate_password_hash(demo_password)
        execute_with_fk_logging(c, """
            INSERT INTO users (name, email, password, department, level, role, is_suspended)
            VALUES (?, ?, ?, ?, ?, 'student', 0)
        """, ("Demo User", demo_email, hashed_pw, "Psychology", "400"))
        demo_user_id = c.lastrowid
        execute_with_fk_logging(c, "INSERT INTO payments (user_id, amount, status) VALUES (?, ?, ?)", (demo_user_id, 20000, "paid"))

    # -------------------------
    # CREATE ADMIN USER
    # -------------------------
    admin_email = "wideminddevs@gmail.com"
    admin_hashed_password = "scrypt:32768:8:1$AMDSiSevHwChJp23$083a029ff1370771a4afd5e72bcb3803bafccdac058f559a997d6641084e6b955489fc4df1678bb19d857516c7c22844601494c0c50e75a56ab90e1c25b46e8e"
    c.execute("SELECT id FROM users WHERE email=?", (admin_email,))
    if not c.fetchone():
        execute_with_fk_logging(c, """
            INSERT INTO users (name, email, password, role, is_suspended)
            VALUES (?, ?, ?, 'admin', 0)
        """, ("Admin Wide", admin_email, admin_hashed_password))

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully.")

# -------------------------
# CHECK IF ADMIN
# -------------------------
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