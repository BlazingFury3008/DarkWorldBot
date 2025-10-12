import sqlite3
import json
from datetime import datetime
from typing import Tuple, List, Optional, Dict

DB_FILE = "characters.db"

# -----------------------------
# Core Database Utilities
# -----------------------------
def execute_query(
    query: str,
    params: tuple = (),
    fetchone: bool = False,
    fetchall: bool = False,
    commit: bool = False,
):
    """General-purpose query executor"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(query, params)

    result = None
    if fetchone:
        result = cur.fetchone()
    elif fetchall:
        result = cur.fetchall()

    if commit:
        conn.commit()

    conn.close()
    return result


def init_db():
    """Initialize database and create tables if missing"""
    execute_query(
        """
        CREATE TABLE IF NOT EXISTS parsed_characters (
            uuid TEXT PRIMARY KEY,
            user_id TEXT,
            data TEXT,
            last_updated TEXT,
            keyword TEXT,
        )
        """,
        commit=True,
    )

# -----------------------------
# Character Operations
# -----------------------------
def save_character_json(uuid: str, user_id: str, data: dict, keyword: str = None):
    """Insert or update a character"""
    execute_query(
        """
        REPLACE INTO parsed_characters (uuid, user_id, data, last_updated, keyword)
        VALUES (?, ?, ?, ?, ?)
        """,
        (uuid, user_id, json.dumps(data), datetime.utcnow().isoformat(), keyword),
        commit=True,
    )


def load_character_json(uuid: str, user_id: str | None = None) -> dict | None:
    """Load character JSON by uuid (optionally filtered by user_id)"""
    if user_id:
        row = execute_query(
            "SELECT data FROM parsed_characters WHERE uuid = ? AND user_id = ?",
            (uuid, user_id),
            fetchone=True,
        )
    else:
        row = execute_query(
            "SELECT data FROM parsed_characters WHERE uuid = ?",
            (uuid,),
            fetchone=True,
        )
    return json.loads(row[0]) if row else None


def get_character_by_json_field(user_id: str, field: str, value: str) -> dict | None:
    """Return character data by matching JSON field in 'data'"""
    row = execute_query(
        f"""
        SELECT data FROM parsed_characters
        WHERE user_id = ? AND json_extract(data, '$.{field}') = ?
        """,
        (user_id, value),
        fetchone=True,
    )
    return json.loads(row[0]) if row else None


def list_characters_for_user(user_id: str) -> list[str]:
    """List character names for a user"""
    rows = execute_query(
        "SELECT json_extract(data, '$.name') FROM parsed_characters WHERE user_id = ?",
        (user_id,),
        fetchall=True,
    )
    return [r[0] for r in rows if r and r[0]]

def list_all_characters() -> list[dict]:
    """List all characters with uuid, name, player_name, and user_id."""
    rows = execute_query(
        "SELECT uuid, user_id, data FROM parsed_characters",
        fetchall=True,
    )

    characters = []
    for r in rows:
        if not r or not r[0] or not r[2]:
            continue
        try:
            data = json.loads(r[2])
        except Exception:
            continue

        characters.append({
            "uuid": r[0],
            "user_id": r[1],
            "name": data.get("name", "Unknown"),
            "player_name": data.get("player_name", "Unknown"),
        })

    return characters

def update_character_field(uuid: str, user_id: str, field: str, value: str) -> bool:
    """Update a single column (not JSON) for a character"""
    query = f"UPDATE parsed_characters SET {field} = ? WHERE uuid = ? AND user_id = ?"
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(query, (value, uuid, user_id))
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated

# -----------------------------
# Thin Wrappers (Convenience)
# -----------------------------
def get_character_by_url(sheet_url: str, user_id: str) -> dict | None:
    """Return character row if a character with the same URL already exists"""
    return get_character_by_json_field(user_id, "SHEET_URL", sheet_url)


def update_character_keyword(uuid: str, user_id: str, new_keyword: str) -> bool:
    """Update the keyword for a specific character"""
    return update_character_field(uuid, user_id, "keyword", new_keyword)


def get_character_uuid_by_name(user_id: str, name: str) -> str | None:
    """Get a character's UUID by name"""
    row = execute_query(
        """
        SELECT uuid FROM parsed_characters
        WHERE user_id = ? AND json_extract(data, '$.name') = ?
        """,
        (user_id, name),
        fetchone=True,
    )
    return row[0] if row else None


def get_characters_for_user(user_id: str) -> list[dict]:
    """Return all characters for a user with name + keyword"""
    rows = execute_query(
        "SELECT data, keyword FROM parsed_characters WHERE user_id = ?",
        (user_id,),
        fetchall=True,
    )
    chars = []
    for data_json, keyword in rows:
        data = json.loads(data_json)
        chars.append({"name": data.get("name"), "keyword": keyword})
    return chars

def get_all_characters() -> list[dict]:
    """Return all characters across all users"""
    rows = execute_query(
        "SELECT uuid, user_id, data, keyword, last_updated FROM parsed_characters",
        fetchall=True,
    )
    chars = []
    for uuid, user_id, data_json, keyword, last_updated in rows:
        data = json.loads(data_json)
        chars.append({
            "uuid": uuid,
            "user_id": user_id,
            "name": data.get("name"),
            "keyword": keyword,
            "last_updated": last_updated,
            "data": data
        })
    return chars

def get_character_by_uuid(uuid: str) -> Optional[dict]:
    """Return single character dict by UUID (parsed JSON data)."""
    rows = execute_query(
        "SELECT data FROM parsed_characters WHERE uuid = ?",
        (uuid,),
        fetchall=True,
    )
    if not rows:
        return None
    try:
        return json.loads(rows[0][0])
    except Exception:
        return None

def get_character_macros(char_id: str) -> Dict[str, str]:
    """Get all dice macros for a given character as a dictionary.

    Args:
        char_id (str): Character UUID

    Returns:
        dict[str, str]: {macro_name: macro_expression} or empty dict if none
    """
    data = get_character_by_uuid(char_id)
    if not data:
        return {}

    macros = data.get("macros")
    if isinstance(macros, dict):
        return macros
    return {}

