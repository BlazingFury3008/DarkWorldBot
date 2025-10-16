import sqlite3
import json
from datetime import datetime
from typing import Optional, Dict, Any

DB_FILE = "characters.db"

# =============================
# Core Database Utilities
# =============================

def execute_query(
    query: str,
    params: tuple = (),
    *,
    fetchone: bool = False,
    fetchall: bool = False,
    commit: bool = False,
) -> Optional[Any]:
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
            user_id TEXT UNIQUE,
            data TEXT,
            last_updated TEXT,
            keyword TEXT
        )
        """,
        commit=True,
    )

    execute_query(
        """
        CREATE TABLE IF NOT EXISTS persona (
            uuid TEXT PRIMARY KEY,
            user_id TEXT,
            name TEXT,
            header TEXT,
            keyword TEXT,
            image BLOB
        )
        """,
        commit=True,
    )

# =============================
# Character Operations
# =============================

def save_character_json(uuid: str, user_id: str, data: dict) -> None:
    """Insert or update a character entry (replaces existing if uuid matches)."""
    execute_query(
        """
        REPLACE INTO parsed_characters (uuid, user_id, data, last_updated)
        VALUES (?, ?, ?, ?)
        """,
        (uuid, user_id, json.dumps(data), datetime.utcnow().isoformat()),
        commit=True,
    )


def load_character_json(uuid: str, user_id: Optional[str] = None) -> Optional[dict]:
    """Load character JSON by uuid (optionally filtered by user_id)."""
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


def get_character_by_json_field(user_id: str, field: str, value: str) -> Optional[dict]:
    """Return character data by matching a JSON field within 'data'."""
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
    """Return a list containing the user's character name (0 or 1 elements)."""
    row = execute_query(
        "SELECT json_extract(data, '$.name') FROM parsed_characters WHERE user_id = ?",
        (user_id,),
        fetchone=True,
    )
    return [row[0]] if row and row[0] is not None else []


def list_all_characters() -> list[dict]:
    """List all characters with uuid, name, player_name, and user_id."""
    rows = execute_query(
        "SELECT uuid, user_id, data FROM parsed_characters",
        fetchall=True,
    )
    characters = []
    for uuid, user_id, data_json in rows:
        if not uuid or not data_json:
            continue
        try:
            data = json.loads(data_json)
        except Exception:
            continue

        characters.append({
            "uuid": uuid,
            "user_id": user_id,
            "name": data.get("name", "Unknown"),
            "player_name": data.get("player_name", "Unknown"),
        })
    return characters


def update_character_field(uuid: str, user_id: str, field: str, value: str) -> bool:
    """Update a single non-JSON field (e.g., keyword) for a character."""
    execute_query(
        f"UPDATE parsed_characters SET {field} = ? WHERE uuid = ? AND user_id = ?",
        (value, uuid, user_id),
        commit=True,
    )
    return True


def get_character_by_url(sheet_url: str, user_id: str) -> Optional[dict]:
    """Return character row if a character with the same URL already exists."""
    return get_character_by_json_field(user_id, "SHEET_URL", sheet_url)


def update_character_keyword(uuid: str, user_id: str, new_keyword: str) -> bool:
    """Update the keyword for a specific character."""
    return update_character_field(uuid, user_id, "keyword", new_keyword)


def get_character_uuid_by_name(user_id: str, name: str) -> Optional[str]:
    """Get a character's UUID by name."""
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
    """Return all characters for a user with name + keyword."""
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
    """Return all characters across all users."""
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
            "data": data,
        })
    return chars


def get_character_by_uuid(uuid: str) -> Optional[dict]:
    """Return single character dict by UUID (parsed JSON data)."""
    row = execute_query(
        "SELECT data FROM parsed_characters WHERE uuid = ?",
        (uuid,),
        fetchone=True,
    )
    return json.loads(row[0]) if row else None


def get_character_macros(char_id: str) -> Dict[str, str]:
    """Get all dice macros for a given character as a dictionary."""
    data = get_character_by_uuid(char_id)
    if not data:
        return {}
    macros = data.get("macros")
    return macros if isinstance(macros, dict) else {}

# =============================
# Persona Operations
# =============================

def create_or_update_persona(uuid: str, user_id: str, header: str, name:str, keyword: Optional[str] = None, image: Optional[bytes] = None) -> None:
    """Insert or update a persona entry."""
    execute_query(
        """
        REPLACE INTO persona (uuid, user_id, header, keyword, image, name)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (uuid, user_id, header, keyword, image, name),
        commit=True,
    )


def get_persona(uuid: str, user_id: Optional[str] = None) -> Optional[dict]:
    """Retrieve a persona by UUID (and optionally user)."""
    if user_id:
        row = execute_query(
            "SELECT uuid, user_id, header, keyword, image, name FROM persona WHERE uuid = ? AND user_id = ?",
            (uuid, user_id),
            fetchone=True,
        )
    else:
        row = execute_query(
            "SELECT uuid, user_id, header, keyword, image, name FROM persona WHERE uuid = ?",
            (uuid,),
            fetchone=True,
        )
    if not row:
        return None
    return {
        "uuid": row[0],
        "user_id": row[1],
        "header": row[2],
        "keyword": row[3],
        "image": row[4],
        "name": row[5],
    }


def list_personas_for_user(user_id: str) -> list[dict]:
    """List all personas for a given user."""
    rows = execute_query(
        "SELECT uuid, header, keyword, name FROM persona WHERE user_id = ?",
        (user_id,),
        fetchall=True,
    )
    return [{"uuid": r[0], "header": r[1], "keyword": r[2], "name": r[3]} for r in rows]


def update_persona_keyword(uuid: str, user_id: str, new_keyword: str) -> bool:
    """Update the keyword for a persona."""
    execute_query(
        "UPDATE persona SET keyword = ? WHERE uuid = ? AND user_id = ?",
        (new_keyword, uuid, user_id),
        commit=True,
    )
    return True


def update_persona_image(uuid: str, user_id: str, new_image: bytes) -> bool:
    """Update the image blob for a persona."""
    execute_query(
        "UPDATE persona SET image = ? WHERE uuid = ? AND user_id = ?",
        (new_image, uuid, user_id),
        commit=True,
    )
    return True


def update_persona_header(uuid: str, user_id: str, new_header: str) -> bool:
    """Update the header for a persona."""
    execute_query(
        "UPDATE persona SET header = ? WHERE uuid = ? AND user_id = ?",
        (new_header, uuid, user_id),
        commit=True,
    )
    return True


def update_persona_name_by_old_name(user_id: str, old_name: str, new_name: str) -> bool:
    """Update the persona name for a given user, matching old name to new name."""
    execute_query(
        "UPDATE persona SET name = ? WHERE user_id = ? AND name = ?",
        (new_name, user_id, old_name),
        commit=True,
    )
    return True


def delete_persona(uuid: str, user_id: str) -> bool:
    """Delete a persona entry."""
    execute_query(
        "DELETE FROM persona WHERE uuid = ? AND user_id = ?",
        (uuid, user_id),
        commit=True,
    )
    return True
