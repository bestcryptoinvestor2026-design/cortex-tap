import sqlite3
from datetime import datetime

def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            total_taps INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована")

def get_user(user_id):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, total_taps FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def update_balance(user_id, taps):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET balance = balance + ?, total_taps = total_taps + ? 
        WHERE user_id = ?
    """, (taps, taps, user_id))
    conn.commit()
    conn.close()

def add_user(user_id, username, first_name):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, username, first_name, balance, total_taps, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user_id, username, first_name, 0, 0, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_top_players(limit=5):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT first_name, balance FROM users 
        ORDER BY balance DESC LIMIT ?
    """, (limit,))
    result = cursor.fetchall()
    conn.close()
    return result

def get_global_stats():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), SUM(total_taps), SUM(balance) FROM users")
    result = cursor.fetchone()
    conn.close()
    return result