import sqlite3
import os
from werkzeug.security import generate_password_hash

# -------------------------
# DATABASE PATH (PERSISTENT)
# -------------------------
DB_PATH = os.environ.get(
    "DATABASE_PATH",
    "/var/data/tutor.db"   # Render persistent disk
)

# -------------------------
# GET DATABASE CONNECTION
# -------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------------
# INITIALIZE DATABASE
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # USERS
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

    # COURSES
    c.execute("""
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_code TEXT UNIQUE NOT NULL,
            course_title TEXT NOT NULL,
            description TEXT
        )
    """)

    # MATERIALS
    c.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL,
            title TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id)
        )
    """)

    # PAYMENTS
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            status TEXT DEFAULT 'unpaid',
            admin_override_status TEXT DEFAULT NULL,
            reference TEXT,
            paid_at DATETIME,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # CONTACT
    c.execute("""
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            subject TEXT,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # NOTIFICATIONS
    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            link TEXT,
            is_read INTEGER DEFAULT 0,
            is_archived INTEGER DEFAULT 0,
            is_critical INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # PUSH
    c.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -------------------------
    # DEMO USER
    # -------------------------
    demo_email = "demo@widemind.test"
    demo_password = "demopassword"

    c.execute("SELECT id FROM users WHERE email=?", (demo_email,))
    if not c.fetchone():
        hashed_pw = generate_password_hash(demo_password)

        c.execute("""
            INSERT INTO users (name, email, password, department, level, role)
            VALUES (?, ?, ?, ?, ?, 'student')
        """, ("Demo User", demo_email, hashed_pw, "Psychology", "400"))

        demo_user_id = c.lastrowid

        c.execute("""
            INSERT INTO payments (user_id, amount, status, reference, paid_at)
            VALUES (?, ?, 'paid', ?, datetime('now'))
        """, (demo_user_id, 2000000, "DEMO-REF-001"))

    # -------------------------
    # ADMIN USER
    # -------------------------
    admin_email = "wideminddevs@gmail.com"

    admin_hashed_password = (
        "scrypt:32768:8:1$AMDSiSevHwJp23$083a029ff1370771a4afd5e72bcb3803"
    )

    c.execute("SELECT id FROM users WHERE email=?", (admin_email,))
    if not c.fetchone():
        c.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (?, ?, ?, 'admin')
        """, ("Admin Wide", admin_email, admin_hashed_password))

    conn.commit()
    conn.close()

    print("✅ Database initialized successfully.")

# -------------------------
# CHECK IF ADMIN
# -------------------------
def is_admin(user_id):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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