import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "tutor.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        department TEXT,
        level TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT UNIQUE NOT NULL,
        course_title TEXT NOT NULL,
        description TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        FOREIGN KEY(course_id) REFERENCES courses(id)
    )
    """)

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

    # seed courses
    c.execute("SELECT id FROM courses WHERE course_code='Psy432'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO courses (course_code, course_title, description) VALUES (?, ?, ?)",
            ("Psy432", "Adolescent Psychology", "Adolescent development")
        )
        cid = c.lastrowid
        c.execute("INSERT INTO materials VALUES (NULL, ?, ?, ?)", (cid, "lesson1.mp3", "audio"))
        c.execute("INSERT INTO materials VALUES (NULL, ?, ?, ?)", (cid, "lesson1.pdf", "pdf"))

    c.execute("SELECT id FROM courses WHERE course_code='Psy409'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO courses (course_code, course_title, description) VALUES (?, ?, ?)",
            ("Psy409", "Biological Psychology", "Neural processes")
        )
        cid = c.lastrowid
        c.execute("INSERT INTO materials VALUES (NULL, ?, ?, ?)", (cid, "lesson2.mp3", "audio"))
        c.execute("INSERT INTO materials VALUES (NULL, ?, ?, ?)", (cid, "lesson2.pdf", "pdf"))

    # ✅ CREATE DEMO USER (CORRECT PLACE)
    c.execute("SELECT id FROM users WHERE email=?", ("demo@widemind.test",))
    if not c.fetchone():
        from werkzeug.security import generate_password_hash

        c.execute(
            "INSERT INTO users (name, email, password, department, level) VALUES (?, ?, ?, ?, ?)",
            (
                "Demo Admin",
                "demo@widemind.test",
                generate_password_hash("demopassword"),
                "Psychology",
                "400"
            )
        )
        demo_user_id = c.lastrowid

        c.execute(
            "INSERT INTO payments (user_id, amount, status) VALUES (?, ?, ?)",
            (demo_user_id, 20000, "paid")
        )

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully.")

def hash_password(password):
    return generate_password_hash(password)

if __name__ == "__main__":
    init_db()
