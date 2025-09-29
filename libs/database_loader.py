import sqlite3, json
from datetime import datetime

DB_FILE = "characters.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS parsed_characters (
        uuid TEXT PRIMARY KEY,
        user_id TEXT,
        data TEXT,
        last_updated TEXT
    )
    """)
    conn.commit()
    conn.close()

def save_character_json(uuid: str, user_id: str, data: dict):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        REPLACE INTO parsed_characters (uuid, user_id, data, last_updated)
        VALUES (?, ?, ?, ?)
    """, (
        uuid,
        user_id,
        json.dumps(data),
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()

def load_character_json(uuid: str, user_id: str) -> dict | None:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT data FROM parsed_characters WHERE uuid = ? AND user_id = ?
    """, (uuid, user_id))
    row = cur.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None
