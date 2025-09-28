import gspread
import logging
import os
import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from typing import Dict, List, Optional
import gspread.utils

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SERVICE_ACCOUNT_FILE = "credentials.json"
DB_FILE = "characters.db"

blood_gen = {
    16: {"max_blood": 10, "bpt": 1},
    15: {"max_blood": 10, "bpt": 1},
    14: {"max_blood": 10, "bpt": 1},
    13: {"max_blood": 10, "bpt": 1},
    12: {"max_blood": 11, "bpt": 1},
    11: {"max_blood": 12, "bpt": 1},
    10: {"max_blood": 13, "bpt": 1},
    9:  {"max_blood": 14, "bpt": 2},
    8:  {"max_blood": 15, "bpt": 3},
    7:  {"max_blood": 20, "bpt": 4},
    6:  {"max_blood": 30, "bpt": 6},
    5:  {"max_blood": 40, "bpt": 8},
    4:  {"max_blood": 50, "bpt": 10},
}

logging.basicConfig(
    level=logging.ERROR,  # Change to INFO in production
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("character_debug.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)


# --- Database Helpers ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS characters (
        uuid TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        character_name TEXT,
        sheet_data TEXT,
        last_updated TEXT
    )
    """)
    conn.commit()
    conn.close()


def save_character_to_db(uuid: str, user_id: str, name: str, sheet_values: List[List[str]]):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "REPLACE INTO characters (uuid, user_id, character_name, sheet_data, last_updated) VALUES (?, ?, ?, ?, ?)",
        (
            uuid,
            user_id,
            name,
            json.dumps(sheet_values),
            datetime.utcnow().isoformat()
        )
    )
    conn.commit()
    conn.close()


def load_character_from_db(uuid: str, user_id: str) -> Optional[Dict]:
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT character_name, sheet_data, last_updated FROM characters WHERE uuid = ? AND user_id = ?", (uuid, user_id))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "character_name": row[0],
            "sheet_values": json.loads(row[1]),
            "last_updated": row[2]
        }
    return None

class Character:

    def __init__(self, str_uuid: Optional[str] = None, user_id: Optional[str] = None, SHEET_URL: str = "", use_cache: bool = True, max_age_minutes: int = 60):
        # Auto-generate uuid if not given
        self.uuid = str_uuid or str(uuid.uuid4())

        # Use empty string if user_id is None
        self.user_id = user_id or ""

        self.SHEET_URL = SHEET_URL
        self.last_updated = None

        # Try loading from DB
        cached = load_character_from_db(self.uuid, user_id) if use_cache else None

        if cached:
            logger.info("Loaded character from DB")
            self.sheet_values = cached["sheet_values"]
            self.last_updated = cached["last_updated"]

                # Refresh if cache is stale
            if self.needs_refresh(max_age_minutes):
                logger.info("Cache is stale → refreshing from Google Sheets")
                self.refetch_data()
        else:
            logger.info("No cache found → fetching from Google Sheets")
            self.refetch_data()

        # Load all parsed data
        self.get_all_data()

    def get_all_data(self):

        # Load fields
        self.name = self.get_cell_value("AS3")
        self.player_name = self.get_cell_value("AS5")
        self.concept = self.get_cell_value("AS8")
        self.nature = self.get_cell_value("AS9")
        self.demeanor = self.get_cell_value("AS10")
        self.ranking = self.get_cell_value("AS12")
        gen_val = self.get_cell_value("AS13")
        try:
            self.generation = int(gen_val)
        except (ValueError, TypeError):
            self.generation = None        
        self.kindred_time = self.get_cell_value("AS14")
        self.age = self.get_cell_value("AS15")
        self.sect = self.get_cell_value("AS17")
        self.clan = self.get_cell_value("AS20")
        self.bane = self.get_cell_value("AS23")

        # Attributes
        self.attributes = [
            self.get_trait(c)
            for c in ["C35", "C37", "C39", "U35", "U37", "U39", "AM35", "AM37", "AM39"]
        ]

        # Abilities
        self.abilities = {
            "Talents": [self.get_trait(f"C{c}") for c in [44, 46, 48, 50, 52, 54, 56, 58, 60, 62]],
            "Skills": [self.get_trait(f"U{c}") for c in [44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64]],
            "Knowledges": [self.get_trait(f"AM{c}") for c in [44, 46, 48, 50, 52, 54, 56, 58, 60, 62, 64]],
        }

        # Disciplines
        self.disciplines = [self.get_dot_trait(f"C{c}", 10) for c in [70,71,72,73,74,77,78,79,80,81,82,83,84,85,86,87]]
        self.disciplines = [val for val in self.disciplines if val and val.get("name")]

        # Backgrounds
        self.backgrounds = [self.get_dot_trait(f"U{c}", 10) for c in range(70, 90)]
        self.backgrounds = [val for val in self.backgrounds if val and val.get("name")]

        self.virtues = [self.get_dot_trait(f"AP{c}", 5) for c in range(69,72)]

        self.path = self.get_dot_trait("AM75", 10)
        self.merits = [self.get_advantage(f"C{c}") for c in range(94,115)]
        self.merits = [val for val in self.merits if val and val.get("name")]
        self.flaws = [self.get_advantage(f"U{c}") for c in range(94,115)]
        self.flaws = [val for val in self.flaws if val and val.get("name")]

        self.max_willpower = self.get_dot_trait("AM78", 10).get("value")
        self.max_blood = blood_gen.get(self.generation).get("max_blood")
        self.blood_per_turn = blood_gen.get(self.generation).get("bpt")

        self.derangments = [self.get_derangement_value(f"AM{c}") for c in range(94,115)]

    def refetch_data(self):
        """Force refresh from Google Sheets and save to DB"""
        client = get_client()
        spreadsheet = client.open_by_url(self.SHEET_URL)
        worksheet = spreadsheet.get_worksheet_by_id(0)
        self.sheet_values = worksheet.get_all_values()
        save_character_to_db(uuid=self.uuid, user_id=self.user_id, name=self.get_cell_value("AS3") or "Unknown", sheet_values=self.sheet_values)
        self.last_updated = datetime.utcnow().isoformat()

    def needs_refresh(self, max_age_minutes: int = 60) -> bool:
        """Check if cached data is older than max_age_minutes"""
        if not self.last_updated:
            return True
        try:
            last_dt = datetime.fromisoformat(self.last_updated)
        except ValueError:
            return True
        return datetime.utcnow() - last_dt > timedelta(minutes=max_age_minutes)

    def get_cell_value(self, cell: str) -> str:
        """Return raw string from cached worksheet at given A1 cell"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            return self.sheet_values[row - 1][col - 1]
        except IndexError:
            return None


    def get_derangement_value(self, cell: str) -> str:
        """Return raw string from cached worksheet at given A1 cell"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            return {
                "name": self.sheet_values[row - 1][col - 1],
                "desc": self.sheet_values[row-1][col + 7]
                }
        except IndexError:
            return None

    def get_dot_trait(self, cell: str, amount: int) -> Dict:
        """Return a dot-based trait {name, value} (for disciplines/backgrounds)"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col - 1]
        except IndexError:
            return {"name": None, "value": 0}

        if not name or name.strip() == "":
            return None

        # Count dots from col+6 to col+15
        values = []
        for c in range(col + 6, col + 6 + amount):
            try:
                values.append(self.sheet_values[row - 1][c - 1])
            except IndexError:
                break
        value_count = sum(1 for v in values if v not in (None, ""))

        if value_count == 0:
            return None

        return {"name": name.strip(), "value": value_count}
    
    def get_advantage(self, cell: str) -> Optional[Dict]:
        """Return an advantage {name, purchase, rating} from a row, starting at the given cell (e.g. 'C94')."""
        row, col = gspread.utils.a1_to_rowcol(cell)  # row=94, col=3 for "C94"

        try:
            # Remember: sheet_values is 0-based [row-1][col-1]
            row_values = self.sheet_values[row - 1]

            name     = row_values[col - 1]          # base col (C)
            purchase = row_values[col - 1 + 11]     # +12 cols → O
            rating   = row_values[col - 1 + 15]     # +16 cols → S
        except IndexError:
            return None

        # Normalize rating
        if isinstance(rating, str):
            rating = rating.strip()
            rating = int(rating) if rating.isdigit() else 0
        elif rating in (None, ""):
            rating = 0

        # Skip invalid rows
        if not name or name.strip() == "" or rating == 0 or not purchase or purchase.strip() == "":
            return None

        return {
            "name": name.strip(),
            "purchase": purchase.strip(),
            "rating": rating,
        }

    
    def get_trait(self, cell: str) -> Dict:
        """Return a trait with optional specialties {name, value, specs}"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col - 1]
        except IndexError:
            return {"name": None, "value": 0, "specs": None}

        if not name or name.strip() == "":
            return None

        # Count dots from col+6 to col+15
        values = []
        for c in range(col + 6, col + 16):
            try:
                values.append(self.sheet_values[row - 1][c - 1])
            except IndexError:
                break
        value_count = sum(1 for v in values if v not in (None, ""))

        # Specialty row+1, col+4
        try:
            specs = self.sheet_values[row][col + 3]

            if specs == "":
                specs = None
        except IndexError:
            specs = None

        return {"name": name.strip(), "value": value_count, "specs": specs}
    

    def __str__(self):
        blood_info = (
            f"{self.max_blood} (BPT: {self.blood_per_turn})"
            if self.max_blood and self.blood_per_turn
            else "Unknown"
        )

        lines = [
            f"*{self.uuid} | {self.user_id}*",
            f"Name: {self.name or 'Unknown'}",
            f"Player: {self.player_name or 'Unknown'}",
            "",
            f"Clan: {self.clan or 'Unknown'}",
            f"Generation: {self.generation or 'Unknown'} ({self.ranking or 'N/A'})",
            f"Sect: {self.sect or 'Unknown'}",
            "",
            f"Age: {self.age or '?'} ({self.kindred_time or '?'} Years since embrace)",
            "",
            f"Bane: {self.bane or 'None'}",
            "",
            f"Max Willpower: {self.max_willpower or 0}",
            f"Max Blood: {blood_info}",
            "",
            "Attributes:",
        ]

        # Attributes
        for trait in self.attributes:
            if trait:
                spec = f" (Specs: {trait['specs']})" if trait.get("specs") else ""
                lines.append(f"    {trait['name']}: {trait['value']}{spec}")

        # Abilities
        lines.append("\nAbilities:")
        for category, traits in self.abilities.items():
            lines.append(f"  {category}:")
            for trait in traits:
                if trait:
                    spec = f" (Specs: {trait['specs']})" if trait.get("specs") else ""
                    lines.append(f"    {trait['name']}: {trait['value']}{spec}")

        # Disciplines
        lines.append("\nDisciplines:")
        if self.disciplines:
            for d in self.disciplines:
                lines.append(f"  {d['name']}: {d['value']}")
        else:
            lines.append("  None")

        # Backgrounds
        lines.append("\nBackgrounds:")
        if self.backgrounds:
            for b in self.backgrounds:
                lines.append(f"  {b['name']}: {b['value']}")
        else:
            lines.append("  None")

        # Virtues
        lines.append("\nVirtues:")
        if self.virtues:
            for v in self.virtues:
                if v:
                    lines.append(f"  {v['name']}: {v['value']}")
        else:
            lines.append("  None")

        # Path
        if self.path:
            lines.append(f"\nPath: {self.path['name']} ({self.path['value']})")

        # Merits
        lines.append("\nMerits:")
        if self.merits:
            for m in self.merits:
                lines.append(f"  {m['name']} ({m['rating']}pt, {m['purchase']})")
        else:
            lines.append("  None")

        # Flaws
        lines.append("\nFlaws:")
        if self.flaws:
            for f in self.flaws:
                lines.append(f"  {f['name']} ({f['rating']}pt, {f['purchase']})")
        else:
            lines.append("  None")

        # Derangements
        lines.append("\nDerangements:")
        if self.derangments:
            for d in self.derangments:
                if d and d.get("name"):
                    lines.append(f"  {d['name']}: {d.get('desc', '')}")
        else:
            lines.append("  None")

        return "\n".join(lines)

    def reset_temp(self):
        self.curr_willpower = self.max_willpower
        self.curr_blood = self.max_blood

if __name__ == "__main__":
    init_db()
    SHEET_URL = "https://docs.google.com/spreadsheets/d/17G7IDHWXJlXqZ5p9Ow-Uh5MSPpXNX9GRXeO8auYSbKk/edit?gid=1568844995#gid=1568844995"

    char = Character(str_uuid="ccd54ca5-5da1-4aa0-9e77-e0cfa8eb3143", user_id="ahh", SHEET_URL=SHEET_URL, use_cache=True)

    print(char)

