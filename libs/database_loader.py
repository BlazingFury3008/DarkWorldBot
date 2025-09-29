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
        last_updated TEXT,
        keyword TEXT
    )
    """)
    conn.commit()
    conn.close()


def save_character_json(uuid: str, user_id: str, data: dict, keyword: str = None):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        REPLACE INTO parsed_characters (uuid, user_id, data, last_updated, keyword)
        VALUES (?, ?, ?, ?, ?)
    """, (
        uuid,
        user_id,
        json.dumps(data),
        datetime.utcnow().isoformat(),
        keyword,
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

def get_character_by_url(sheet_url: str, user_id: str):
    """Return character row if a character with the same URL already exists"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        SELECT data FROM parsed_characters
        WHERE user_id = ? AND json_extract(data, '$.SHEET_URL') = ?
    """, (user_id, sheet_url))
    row = cur.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None


def list_characters_for_user(user_id: str) -> list[str]:
    conn = sqlite3.connect("characters.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT json_extract(data, '$.name') FROM parsed_characters WHERE user_id = ?",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]

def update_character_keyword(uuid: str, user_id: str, new_keyword: str) -> bool:
    """Update the keyword for a specific character"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "UPDATE parsed_characters SET keyword = ? WHERE uuid = ? AND user_id = ?",
        (new_keyword, uuid, user_id),
    )
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated

def get_character_uuid_by_name(user_id: str, name: str) -> str | None:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT uuid FROM parsed_characters WHERE user_id = ? AND json_extract(data, '$.name') = ?",
        (user_id, name),
    )
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def get_characters_for_user(user_id: str) -> list[dict]:
    """Return all characters for a user with name + keyword"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT data, keyword FROM parsed_characters WHERE user_id = ?",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()

    chars = []
    for data_json, keyword in rows:
        data = json.loads(data_json)
        chars.append({
            "name": data.get("name"),
            "keyword": keyword  # ✅ use column, not JSON
        })
    return chars