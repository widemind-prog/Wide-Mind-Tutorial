import os
import libsql_experimental as libsql
from werkzeug.security import generate_password_hash


# -----------------------
# TURSO CONNECTION
# -----------------------
TURSO_URL = os.environ.get("TURSO_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")


# -----------------------
# GET DB CONNECTION
# -----------------------
def get_db():
    conn = libsql.connect(
        database=TURSO_URL,
        auth_token=TURSO_AUTH_TOKEN
    )
    return conn


# -----------------------
# INITIALIZE DATABASE
# -----------------------
def init_db():
    conn = get_db()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        department TEXT,
        level TEXT,
        role TEXT DEFAULT 'student',
        is_suspended INTEGER DEFAULT 0,
        push_enabled INTEGER DEFAULT 0
    )""")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS courses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT UNIQUE NOT NULL,
        course_title TEXT NOT NULL,
        description TEXT
    )""")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        title TEXT NOT NULL,
        FOREIGN KEY(course_id) REFERENCES courses(id)
    )""")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT DEFAULT 'unpaid',
        admin_override_status TEXT DEFAULT NULL,
        reference TEXT,
        paid_at DATETIME,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS contact_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        subject TEXT,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    conn.execute("""
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
    )""")

    conn.execute("""
    CREATE TABLE IF NOT EXISTS push_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        endpoint TEXT NOT NULL,
        p256dh TEXT NOT NULL,
        auth TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")

    conn.commit()
    print("Database initialized successfully.")


# -----------------------
# CHECK IF ADMIN
# -----------------------
def is_admin(user_id):
    conn = get_db()
    result = conn.execute(
        "SELECT role FROM users WHERE id=?", (user_id,)
    ).fetchone()
    return result and result[0] == "admin"


def hash_password(password):
    return generate_password_hash(password)


if __name__ == "__main__":
    init_db()
