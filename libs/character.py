import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import gspread
import gspread.utils
from google.oauth2.service_account import Credentials

from libs.database_loader import *
from libs.sheet_loader import *

# Setup logger
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,  # or DEBUG if you want more detail
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Blood pool generation table
blood_gen = {
    16: {"max_blood": 10, "bpt": 1},
    15: {"max_blood": 10, "bpt": 1},
    14: {"max_blood": 10, "bpt": 1},
    13: {"max_blood": 10, "bpt": 1},
    12: {"max_blood": 11, "bpt": 1},
    11: {"max_blood": 12, "bpt": 1},
    10: {"max_blood": 13, "bpt": 1},
    9: {"max_blood": 14, "bpt": 2},
    8: {"max_blood": 15, "bpt": 3},
    7: {"max_blood": 20, "bpt": 4},
    6: {"max_blood": 30, "bpt": 6},
    5: {"max_blood": 40, "bpt": 8},
    4: {"max_blood": 50, "bpt": 10},
}


class Character:
    def __init__(
        self,
        str_uuid: Optional[str] = None,
        user_id: Optional[str] = None,
        SHEET_URL: str = "",
        use_cache: bool = True,
        max_age_minutes: int = 60,
    ):
        self.uuid = str_uuid or str(uuid.uuid4())
        self.user_id = user_id or ""
        self.SHEET_URL = SHEET_URL
        self.last_updated = None

        cached = load_character_json(self.uuid, self.user_id) if use_cache else None

        if cached:
            logger.info("Loaded parsed character from DB")
            for k, v in cached.items():
                setattr(self, k, v)
            self.last_updated = datetime.utcnow().isoformat()
        else:
            logger.info("No cached character → fetching from Google Sheets")
            client = get_client()
            spreadsheet = client.open_by_url(self.SHEET_URL)
            worksheet = spreadsheet.get_worksheet_by_id(0)
            self.sheet_values = worksheet.get_all_values()
            self.get_all_data()
            logger.info("All data gathered")

    # ----------------------------
    # Data Loading
    # ----------------------------

    def refetch_data(self):
        """Force refresh from Google Sheets, re-parse, and save into DB"""
        client = get_client()
        spreadsheet = client.open_by_url(self.SHEET_URL)
        worksheet = spreadsheet.get_worksheet_by_id(0)

        # Always fetch fresh sheet values
        self.sheet_values = worksheet.get_all_values()

        # Parse everything into attributes
        self.get_all_data()

        # Save parsed version into DB
        data = {
            k: v
            for k, v in self.__dict__.items()
            if k not in ("sheet_values",)  # don’t save raw sheet values
        }
        save_character_json(self.uuid, self.user_id, data)

        # Update timestamp
        self.last_updated = datetime.utcnow().isoformat()

    @classmethod
    def load_by_name(cls, name: str, user_id: str) -> Optional["Character"]:
        """Load a character by name and user_id from the DB."""
        conn = sqlite3.connect("characters.db")
        cur = conn.cursor()
        cur.execute(
            """
            SELECT data FROM parsed_characters
            WHERE user_id = ? AND json_extract(data, '$.name') = ?
            """,
            (user_id, name),
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return None

        data = json.loads(row[0])

        # Bypass __init__ so we don't refetch from Sheets
        char = cls.__new__(cls)
        for k, v in data.items():
            setattr(char, k, v)

        return char

    def needs_refresh(self, max_age_minutes: int = 60) -> bool:
        """Check if cached data is older than max_age_minutes"""
        if not self.last_updated:
            return True
        try:
            last_dt = datetime.fromisoformat(self.last_updated)
        except ValueError:
            return True
        return datetime.utcnow() - last_dt > timedelta(minutes=max_age_minutes)

    # ----------------------------
    # Core Parsing Methods
    # ----------------------------

    def get_cell_value(self, cell: str) -> Optional[str]:
        """Return raw string from cached worksheet at given A1 cell"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            return self.sheet_values[row - 1][col - 1]
        except IndexError:
            return None

    def get_derangement_value(self, cell: str) -> Optional[Dict]:
        """Return a derangement {name, desc} from given cell"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            return {
                "name": self.sheet_values[row - 1][col - 1],
                "desc": self.sheet_values[row - 1][col + 7],
            }
        except IndexError:
            return None

    def get_dot_trait(self, cell: str, amount: int) -> Optional[Dict]:
        """Return a dot-based trait {name, value} (for disciplines/backgrounds)"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col - 1]
        except IndexError:
            return {"name": None, "value": 0}

        if not name or name.strip() == "":
            return None

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
        """Return an advantage {name, purchase, rating} from given cell"""
        row, col = gspread.utils.a1_to_rowcol(cell)

        try:
            row_values = self.sheet_values[row - 1]
            name = row_values[col - 1]
            purchase = row_values[col - 1 + 11]  # +12 cols
            rating = row_values[col - 1 + 15]  # +16 cols
        except IndexError:
            return None

        # Normalize rating
        if isinstance(rating, str):
            rating = rating.strip()
            rating = int(rating) if rating.isdigit() else 0
        elif rating in (None, ""):
            rating = 0

        # Skip invalid rows
        if (
            not name
            or name.strip() == ""
            or rating == 0
            or not purchase
            or purchase.strip() == ""
        ):
            return None

        return {"name": name.strip(), "purchase": purchase.strip(), "rating": rating}

    def get_trait(self, cell: str) -> Optional[Dict]:
        """Return a trait with optional specialties {name, value, specs}"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col - 1]
        except IndexError:
            return {"name": None, "value": 0, "specs": None}

        if not name or name.strip() == "":
            return None

        values = []
        for c in range(col + 6, col + 16):
            try:
                values.append(self.sheet_values[row - 1][c - 1])
            except IndexError:
                break
        value_count = sum(1 for v in values if v not in (None, ""))

        # Specialty
        try:
            specs = self.sheet_values[row][col + 3]
            specs = specs if specs else None
        except IndexError:
            specs = None

        return {"name": name.strip(), "value": value_count, "specs": specs}
    
    def get_combo_discipline(self, cell: str) -> str:
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row-1][col-1]
            return name
        except IndexError:
            return None

    def get_ritual(self, cell:str) -> Optional[Dict]:
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row-1][col]
            level = self.sheet_values[row-1][col - 1]
            sorc_type = self.sheet_values[row-1][col+10]
            
            return {
                "name": name,
                "level": level,
                "sorc_type": sorc_type
            }
        except IndexError:
            return {
                "name": None,
                "level": None,
                "sorc_type": None
            }
            
    def get_magic_path(self, cell:str) -> Optional[Dict]:
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            type = self.sheet_values[row-1][col-1]
            name = self.sheet_values[row-1][col +2]
            values = []
            for c in range(col + 12, col + 17):
                try:
                    values.append(self.sheet_values[row - 1][c - 1])
                except IndexError:
                    break
            value_count = sum(1 for v in values if v not in (None, ""))
                
            return {
                "name": name,
                "type": type,
                "level": value_count
            }
        except IndexError:
            return {
                "name": None,
                "type": None,
                "level": None
            }
            

    # ----------------------------
    # Data Assembly
    # ----------------------------

    def get_all_data(self):
        """Parse all data fields from sheet_values into attributes"""
        # Core info
        self.name = self.get_cell_value("AS3")
        self.player_name = self.get_cell_value("AS5")
        self.concept = self.get_cell_value("AS8")
        self.nature = self.get_cell_value("AS9")
        self.demeanor = self.get_cell_value("AS10")
        self.ranking = self.get_cell_value("AS12")

        try:
            self.generation = int(self.get_cell_value("AS13"))
        except (ValueError, TypeError):
            self.generation = None

        self.kindred_time = self.get_cell_value("AS14")
        self.age = self.get_cell_value("AS15")
        self.sect = self.get_cell_value("AS17")
        self.clan = self.get_cell_value("AS20")
        self.bane = self.get_cell_value("AM23")

        # Attributes
        self.attributes = [
            self.get_trait(c)
            for c in ["C35", "C37", "C39", "U35", "U37", "U39", "AM35", "AM37", "AM39"]
        ]

        # Abilities
        self.abilities = {
            "Talents": [self.get_trait(f"C{c}") for c in range(44, 63, 2)],
            "Skills": [self.get_trait(f"U{c}") for c in range(44, 65, 2)],
            "Knowledges": [self.get_trait(f"AM{c}") for c in range(44, 65, 2)],
            "Hobby Talents": [self.get_trait(f"C{c}") for c in range(70, 77, 2)],
            "Professional Skill": [self.get_trait(f"U{c}") for c in range(70, 77, 2)],
            "Expert Knowledge": [self.get_trait(f"AM{c}") for c in range(70, 77, 2)],
        }

        # Disciplines
        self.disciplines = [
            self.get_dot_trait(f"C{c}", 10)
            for c in list(range(83, 88)) + list(range(90, 103))
        ]
        self.disciplines = [d for d in self.disciplines if d and d.get("name")]

        # Backgrounds
        self.backgrounds = [self.get_dot_trait(f"U{c}", 10) for c in range(83, 103)]
        self.backgrounds = [b for b in self.backgrounds if b and b.get("name")]

        # Virtues
        self.virtues = [self.get_dot_trait(f"AP{c}", 5) for c in range(82, 85)]

        # Path
        self.path = self.get_dot_trait("AM88", 10)

        # Merits & Flaws
        self.merits = [self.get_advantage(f"C{c}") for c in range(107, 128)]
        self.merits = [m for m in self.merits if m and m.get("name")]

        self.flaws = [self.get_advantage(f"U{c}") for c in range(107, 128)]
        self.flaws = [f for f in self.flaws if f and f.get("name")]

        # Derived stats
        self.max_willpower = self.get_dot_trait("AM91", 10).get("value")
        self.max_blood = blood_gen.get(self.generation, {}).get("max_blood")
        self.blood_per_turn = blood_gen.get(self.generation, {}).get("bpt")

        # Derangements
        self.derangments = [
            self.get_derangement_value(f"AM{c}") for c in range(107, 128)
        ]
        
        self.combo_disciplines = [
            self.get_combo_discipline(f"C{c}") for c in range(132,295)
        ]
        self.combo_disciplines = [c for c in self.combo_disciplines if c]

        self.rituals = [
            self.get_ritual(f"U{c}") for c in range(132,295)
        ]
        self.rituals = [r for r in self.rituals if r and r.get("name")]

        self.magic_paths = [
            self.get_magic_path(f"AM{c}") for c in range(132,295)
        ]
        self.magic_paths = [p for p in self.magic_paths if p and p.get("name")]


    # ----------------------------
    # Utility
    # ----------------------------

    def refetch_data(self):
        """Fetch fresh data from Google Sheets, parse, and save to DB"""
        client = get_client()
        spreadsheet = client.open_by_url(self.SHEET_URL)
        worksheet = spreadsheet.get_worksheet_by_id(0)
        self.sheet_values = worksheet.get_all_values()

        # Parse everything
        self.get_all_data()
        # Save parsed dict to DB
        self.save_parsed(update=True)

    def save_parsed(self, keyword: str = None, update=True):
            data = {
                k: v for k, v in self.__dict__.items()
                if k not in ("sheet_values",)
            }

            # Auto-generate keyword if not passed
            if not keyword:
                keyword = (self.name or self.uuid).lower().replace(" ", "")

            save_character_json(self.uuid, self.user_id, data, keyword)
            return 0


    def to_dict(self) -> dict:
        """Return a JSON-safe dict representation of the character"""
        return {
            "uuid": self.uuid,
            "user_id": self.user_id,
            "name": getattr(self, "name", None),
            "player_name": getattr(self, "player_name", None),
            "concept": getattr(self, "concept", None),
            "clan": getattr(self, "clan", None),
            "generation": getattr(self, "generation", None),
            "sect": getattr(self, "sect", None),
            "attributes": getattr(self, "attributes", []),
            "abilities": getattr(self, "abilities", {}),
            "disciplines": getattr(self, "disciplines", []),
            "backgrounds": getattr(self, "backgrounds", []),
            "virtues": getattr(self, "virtues", []),
            "path": getattr(self, "path", None),
            "merits": getattr(self, "merits", []),
            "flaws": getattr(self, "flaws", []),
            "derangements": getattr(self, "derangments", []),
            "combo_disciplines": getattr(self, "combo_disciplines", []),
            "rituals": getattr(self, "rituals", []),
            "magic_paths": getattr(self, "magic_paths", []),
            "max_willpower": getattr(self, "max_willpower", 0),
            "max_blood": getattr(self, "max_blood", 0),
            "blood_per_turn": getattr(self, "blood_per_turn", 0),
        }

    @classmethod
    def load_parsed(cls, uuid: str, user_id: str) -> Optional["Character"]:
        """Load from parsed DB only, without hitting Google Sheets"""
        data = load_character_json(uuid, user_id)
        if not data:
            return None

        # Bypass __init__
        char = cls.__new__(cls)
        # Restore everything we saved
        for k, v in data.items():
            setattr(char, k, v)

        return char

    def __str__(self) -> str:
        """Nicely formatted character summary"""
        blood_info = (
            f"{self.max_blood} (BPT: {self.blood_per_turn})"
            if self.max_blood and self.blood_per_turn
            else "Unknown"
        )

        # Header / Basic Info
        lines = [
            f"Character [{self.uuid}] (User: {self.user_id or 'N/A'})",
            "=" * 50,
            f"Name: {self.name or 'Unknown'}",
            f"Player: {self.player_name or 'Unknown'}",
            f"Concept: {self.concept or 'Unknown'}",
            f"Clan: {self.clan or 'Unknown'}",
            f"Generation: {self.generation or 'Unknown'} ({self.ranking or 'N/A'})",
            f"Sect: {self.sect or 'Unknown'}",
            f"Age: {self.age or '?'} ({self.kindred_time or '?'} years since Embrace)",
            f"Bane: {self.bane or 'None'}",
            "",
            f"Max Willpower: {self.max_willpower or 0}",
            f"Blood Pool: {blood_info}",
            "=" * 50,
            "",
        ]

        # Helper to format trait groups
        def format_traits(title: str, traits: List[Dict], indent: int = 2) -> List[str]:
            section = [f"{title}:"]
            if not traits:
                section.append(" " * indent + "None")
                return section
            for t in traits:
                if not t:
                    continue
                spec = f" (Specs: {t['specs']})" if t.get("specs") else ""
                val = f": {t['value']}" if "value" in t and t["value"] is not None else ""
                section.append(" " * indent + f"{t['name']}{val}{spec}")
            return section

        # Helper for simple lists (e.g. combo disciplines)
        def format_list(title: str, items: List[str], indent: int = 2) -> List[str]:
            section = [f"{title}:"]
            if not items:
                section.append(" " * indent + "None")
                return section
            for i in items:
                section.append(" " * indent + str(i))
            return section

        # Helper for rituals and magic paths
        def format_dict_list(title: str, items: List[Dict], fields: List[str], indent: int = 2) -> List[str]:
            section = [f"{title}:"]
            if not items:
                section.append(" " * indent + "None")
                return section
            for item in items:
                parts = [f"{field.capitalize()}: {item.get(field, '')}" for field in fields if item.get(field)]
                section.append(" " * indent + " | ".join(parts))
            return section

        # Sections
        lines.extend(format_traits("Attributes", self.attributes))
        for category, traits in self.abilities.items():
            lines.extend(format_traits(category, traits))
        lines.extend(format_traits("Disciplines", self.disciplines))
        lines.extend(format_traits("Backgrounds", self.backgrounds))
        lines.extend(format_traits("Virtues", self.virtues))

        if self.path:
            lines.append(f"\nPath: {self.path['name']} ({self.path['value']})")

        # Merits & Flaws
        lines.append("\nMerits:")
        if self.merits:
            for m in self.merits:
                lines.append(f"  {m['name']} ({m['rating']}pt, {m['purchase']})")
        else:
            lines.append("  None")

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

        # Combo Disciplines
        lines.extend(format_list("\nCombo Disciplines", self.combo_disciplines))

        # Rituals
        lines.extend(format_dict_list("\nRituals", self.rituals, ["name", "level", "sorc_type"]))

        # Magic Paths
        lines.extend(format_dict_list("\nMagic Paths", self.magic_paths, ["type", "name", "level"]))

        return "\n".join(lines)

    def reset_temp(self):
        """Reset temporary values like current willpower and blood"""
        self.curr_willpower = self.max_willpower
        self.curr_blood = self.max_blood
