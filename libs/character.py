import logging
import json
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import discord
import gspread
import gspread.utils
from google.oauth2.service_account import Credentials  # noqa: F401  # (kept for external get_client impl)

from libs.database_loader import (
    save_character_json,
    load_character_json,
    list_characters_for_user,
)
from libs.sheet_loader import get_client

# --------------------------------------------------------------------------------------
# Logging Setup
# --------------------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# If your app sets up logging globally elsewhere, you can comment out basicConfig below.
logging.basicConfig(
    level=logging.INFO,  # change to logging.DEBUG for more detail
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# --------------------------------------------------------------------------------------
# Constants / Tables
# --------------------------------------------------------------------------------------

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
    """
    Represents a character parsed from a Google Sheet and cached in a local DB.
    Provides utilities to refresh from Sheets, parse fields, and write XP/DTA logs.

    Logging:
      - Every public action emits structured logs with UUID, user_id, and name (if available).
      - Errors use logger.exception to include stack traces.
    """

    # ----------------------------------------------------------------------------------
    # Lifecycle / Init
    # ----------------------------------------------------------------------------------

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
        self.last_updated: Optional[str] = None

        # Runtime fields / counters
        self.curr_blood = 0
        self.curr_willpower = 0
        self.curr_dta = 0
        self.total_dta = 0
        self.curr_xp = 0
        self.total_xp = 0

        # Logs
        self.dta_log: List[Dict] = []
        self.blood_log: List[Dict] = []
        self.xp_log: List[Dict] = []

        # Parsed Sheet Values cache
        self.sheet_values: List[List[str]] = []

        logger.info(self._ctx("INIT - Initializing Character"))

        cached = load_character_json(self.uuid, self.user_id) if use_cache else None

        if cached:
            logger.info(self._ctx("CACHE - Loaded parsed character from DB"))
            for k, v in cached.items():
                setattr(self, k, v)
            self.last_updated = datetime.utcnow().isoformat()
            logger.debug(self._ctx("CACHE - Attributes restored from DB"))
        else:
            # Validate Sheet URL early
            if not self.SHEET_URL or not self.SHEET_URL.startswith("http"):
                logger.error(self._ctx("INIT - Invalid or missing Google Sheet URL"))
                raise ValueError(
                    "The provided Google Sheet URL is missing or invalid. "
                    "Please provide a valid Google Sheets link."
                )

            try:
                logger.info(self._ctx("SHEETS - Opening Google Sheet (no cache)"))
                client = get_client()
                spreadsheet = client.open_by_url(self.SHEET_URL)
                worksheet = spreadsheet.get_worksheet_by_id(0)
                self.sheet_values = worksheet.get_all_values()
                logger.info(
                    self._ctx(
                        f"SHEETS - Loaded {len(self.sheet_values)} rows from worksheet id=0"
                    )
                )
            except Exception as e:
                logger.exception(self._ctx(f"SHEETS - Failed to open or read sheet: {e}"))
                raise ValueError(
                    "Unable to open the provided Google Sheet. "
                    "Please check that the URL is correct and publicly accessible."
                ) from e

            # Parse from sheet
            logger.info(self._ctx("PARSE - Parsing sheet into attributes"))
            self.get_all_data()

            # Initialize current pools from derived maximums
            self.curr_blood = self.max_blood
            self.curr_willpower = self.max_willpower

            # Persist parsed data
            self.save_parsed(update=False)
            logger.info(self._ctx("INIT - Initial parse complete and saved to DB"))

    # ----------------------------------------------------------------------------------
    # Context helper for logging
    # ----------------------------------------------------------------------------------

    def _ctx(self, msg: str) -> str:
        """Include UUID, name (if known), and user context in log lines."""
        name = getattr(self, "name", None) or "Unknown"
        return f"[uuid={self.uuid} user={self.user_id or 'N/A'} name={name}] {msg}"

    # ----------------------------------------------------------------------------------
    # Refresh / Save
    # ----------------------------------------------------------------------------------

    def needs_refresh(self, max_age_minutes: int = 60) -> bool:
        """Check if cached data is older than max_age_minutes"""
        if not self.last_updated:
            logger.debug(self._ctx("REFRESH - No last_updated timestamp, needs refresh"))
            return True
        try:
            last_dt = datetime.fromisoformat(self.last_updated)
        except ValueError:
            logger.warning(self._ctx("REFRESH - Invalid last_updated format, needs refresh"))
            return True
        needs = datetime.utcnow() - last_dt > timedelta(minutes=max_age_minutes)
        logger.debug(self._ctx(f"REFRESH - needs_refresh={needs} (age={(datetime.utcnow()-last_dt)})"))
        return needs

    def refetch_data(self):
        """
        Fetch fresh data from Google Sheets, parse, and save to DB.
        """
        logger.info(self._ctx("REFETCH - Fetch fresh data from sheets"))
        try:
            client = get_client()
            spreadsheet = client.open_by_url(self.SHEET_URL)
            worksheet = spreadsheet.get_worksheet_by_id(0)
            self.sheet_values = worksheet.get_all_values()
            logger.info(self._ctx(f"REFETCH - Loaded {len(self.sheet_values)} rows from sheet"))
        except Exception as e:
            logger.exception(self._ctx(f"REFETCH - Failed to refetch data: {e}"))
            raise

        try:
            # Parse everything
            logger.info(self._ctx("PARSE - Re-parsing sheet after refetch"))
            self.get_all_data()
            # Save parsed dict to DB
            self.save_parsed(update=True)
            logger.info(self._ctx("REFETCH - Re-parse complete and saved"))
        except Exception as e:
            logger.exception(self._ctx(f"REFETCH - Failed during parse/save: {e}"))
            raise

    def save_parsed(self, update: bool = True) -> int:
        """
        Save the current object (minus sheet_values) to the parsed DB.
        """
        try:
            data = {k: v for k, v in self.__dict__.items() if k not in ("sheet_values",)}
            save_character_json(self.uuid, self.user_id, data)
            self.last_updated = datetime.utcnow().isoformat()
            logger.info(self._ctx(f"SAVE - Parsed character saved (update={update})"))
            return 0
        except Exception as e:
            logger.exception(self._ctx(f"SAVE - Failed to save parsed character: {e}"))
            raise

    # ----------------------------------------------------------------------------------
    # Static / Class loaders
    # ----------------------------------------------------------------------------------

    @classmethod
    def load_by_name(cls, name: str, user_id: str) -> Optional["Character"]:
        """
        Load a character by name and user_id from the parsed DB only (no Sheets).
        """
        logger.info(f"[Character.load_by_name] user={user_id} name={name} - Loading from DB")
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
            logger.warning(f"[Character.load_by_name] user={user_id} name={name} - Not found")
            return None

        try:
            data = json.loads(row[0])
        except Exception as e:
            logger.exception(f"[Character.load_by_name] Failed to decode JSON: {e}")
            return None

        # Bypass __init__ so we don't refetch from Sheets
        char = cls.__new__(cls)
        for k, v in data.items():
            setattr(char, k, v)
        logger.info(f"[Character.load_by_name] user={user_id} name={name} - Loaded successfully (uuid={getattr(char,'uuid','?')})")
        return char

    @classmethod
    def load_for_user(cls, user_id: str) -> Optional["Character"]:
        """
        Load the first listed character for a user from the parsed DB.
        """
        logger.info(f"[Character.load_for_user] user={user_id} - Listing characters")
        names = list_characters_for_user(user_id)
        name = names[0] if names else None
        if not name:
            logger.warning(f"[Character.load_for_user] user={user_id} - No characters found")
            return None
        logger.info(f"[Character.load_for_user] user={user_id} - Loading name={name}")
        return cls.load_by_name(name, user_id)

    @classmethod
    def load_parsed(cls, uuid: str, user_id: Optional[str] = None) -> Optional["Character"]:
        """
        Load from parsed DB only, without hitting Google Sheets.
        """
        logger.info(f"[Character.load_parsed] uuid={uuid} user={user_id or 'N/A'} - Loading parsed")
        data = load_character_json(uuid, user_id)
        if not data:
            logger.warning(f"[Character.load_parsed] uuid={uuid} - Not found")
            return None

        char = cls.__new__(cls)
        for k, v in data.items():
            setattr(char, k, v)
        logger.info(f"[Character.load_parsed] uuid={uuid} - Loaded successfully (name={getattr(char,'name','Unknown')})")
        return char

    # ----------------------------------------------------------------------------------
    # Low-level sheet helpers
    # ----------------------------------------------------------------------------------

    def get_cell_value(self, cell: str) -> Optional[str]:
        """Return raw string from cached worksheet at given A1 cell"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            return self.sheet_values[row - 1][col - 1]
        except IndexError:
            logger.debug(self._ctx(f"GET - Cell {cell} out of range"))
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
            logger.debug(self._ctx(f"GET - Derangement base at {cell} out of range"))
            return None

    def get_dot_trait(self, cell: str, amount: int) -> Optional[Dict]:
        """Return a dot-based trait {name, value} (for disciplines/backgrounds)"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col - 1]
        except IndexError:
            logger.debug(self._ctx(f"GET - Dot trait name at {cell} out of range"))
            return {"name": None, "value": 0}

        if not name or str(name).strip() == "":
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

        return {"name": str(name).strip(), "value": value_count}

    def get_advantage(self, cell: str) -> Optional[Dict]:
        """Return an advantage {name, purchase, rating} from given cell"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            row_values = self.sheet_values[row - 1]
            name = row_values[col - 1]
            purchase = row_values[col - 1 + 11]  # +12 cols
            rating = row_values[col - 1 + 15]    # +16 cols
        except IndexError:
            logger.debug(self._ctx(f"GET - Advantage row at {cell} out of range"))
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
            or str(name).strip() == ""
            or rating == 0
            or not purchase
            or str(purchase).strip() == ""
        ):
            return None

        return {"name": str(name).strip(), "purchase": str(purchase).strip(), "rating": rating}

    def get_trait(self, cell: str) -> Optional[Dict]:
        """Return a trait with optional specialties {name, value, specs}"""
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col - 1]
        except IndexError:
            logger.debug(self._ctx(f"GET - Trait name at {cell} out of range"))
            return {"name": None, "value": 0, "specs": None}

        if not name or str(name).strip() == "":
            return None

        values = []
        for c in range(col + 6, col + 16):
            try:
                values.append(self.sheet_values[row - 1][c - 1])
            except IndexError:
                break
        value_count = sum(1 for v in values if v not in (None, ""))

        # Specialty (row below, col + 3)
        try:
            specs = self.sheet_values[row][col + 3]
            specs = specs if specs else None
        except IndexError:
            specs = None

        clean_name = str(name).split("*", 1)[0].strip() if name else ""
        return {"name": clean_name, "value": value_count, "specs": specs}

    def get_combo_discipline(self, cell: str) -> Optional[str]:
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col - 1]
            return name if name not in (None, "") else None
        except IndexError:
            return None

    def get_ritual(self, cell: str) -> Optional[Dict]:
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col]
            level = self.sheet_values[row - 1][col - 1]
            sorc_type = self.sheet_values[row - 1][col + 9]
            if not name:
                return None
            return {"name": name, "level": level, "sorc_type": sorc_type}
        except IndexError:
            return {"name": None, "level": None, "sorc_type": None}

    def get_magic_path(self, cell: str) -> Optional[Dict]:
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            type_ = self.sheet_values[row - 1][col - 1]
            name = self.sheet_values[row - 1][col + 2]
            values = []
            for c in range(col + 12, col + 17):
                try:
                    values.append(self.sheet_values[row - 1][c - 1])
                except IndexError:
                    break
            value_count = sum(1 for v in values if v not in (None, ""))
            if not name:
                return None
            return {"name": name, "type": type_, "level": value_count}
        except IndexError:
            return {"name": None, "type": None, "level": None}

    # ----------------------------------------------------------------------------------
    # Data Assembly
    # ----------------------------------------------------------------------------------

    def get_all_data(self):
        """
        Parse all data fields from sheet_values into attributes.
        """
        logger.info(self._ctx("PARSE - Begin parsing all data blocks"))

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

        logger.debug(self._ctx(f"PARSE - Core name={self.name} clan={self.clan} gen={self.generation}"))

        # Attributes
        self.attributes = [
            self.get_trait(c)
            for c in ["C35", "C37", "C39", "U35", "U37", "U39", "AM35", "AM37", "AM39"]
        ]
        logger.debug(self._ctx(f"PARSE - Attributes parsed ({len([a for a in self.attributes if a])})"))

        # Abilities
        self.abilities = {
            "Talents": [self.get_trait(f"C{c}") for c in range(44, 63, 2)],
            "Skills": [self.get_trait(f"U{c}") for c in range(44, 65, 2)],
            "Knowledges": [self.get_trait(f"AM{c}") for c in range(44, 65, 2)],
            "Hobby Talents": [self.get_trait(f"C{c}") for c in range(70, 77, 2)],
            "Professional Skill": [self.get_trait(f"U{c}") for c in range(70, 77, 2)],
            "Expert Knowledge": [self.get_trait(f"AM{c}") for c in range(70, 77, 2)],
        }
        logger.debug(self._ctx("PARSE - Abilities parsed"))

        # Disciplines
        self.disciplines = [
            self.get_dot_trait(f"C{c}", 10)
            for c in list(range(83, 88)) + list(range(90, 103))
        ]
        self.disciplines = [d for d in self.disciplines if d and d.get("name")]
        logger.debug(self._ctx(f"PARSE - Disciplines parsed count={len(self.disciplines)}"))

        # Backgrounds
        self.backgrounds = [self.get_dot_trait(f"U{c}", 10) for c in range(83, 103)]
        self.backgrounds = [b for b in self.backgrounds if b and b.get("name")]
        logger.debug(self._ctx(f"PARSE - Backgrounds parsed count={len(self.backgrounds)}"))

        # Virtues
        self.virtues = [self.get_dot_trait(f"AP{c}", 5) for c in range(82, 85)]
        logger.debug(self._ctx(f"PARSE - Virtues parsed count={len([v for v in self.virtues if v])}"))

        # Path
        self.path = self.get_dot_trait("AM88", 10)
        logger.debug(self._ctx(f"PARSE - Path parsed {self.path}"))

        # Merits & Flaws
        self.merits = [self.get_advantage(f"C{c}") for c in range(107, 128)]
        self.merits = [m for m in self.merits if m and m.get("name")]

        self.flaws = [self.get_advantage(f"U{c}") for c in range(107, 128)]
        self.flaws = [f for f in self.flaws if f and f.get("name")]
        logger.debug(self._ctx(f"PARSE - Merits={len(self.merits)} Flaws={len(self.flaws)}"))

        # Derived stats
        try:
            self.max_willpower = self.get_dot_trait("AM91", 11).get("value")
        except Exception:
            self.max_willpower = 0

        self.max_blood = blood_gen.get(self.generation, {}).get("max_blood")
        self.blood_per_turn = blood_gen.get(self.generation, {}).get("bpt")
        logger.debug(self._ctx(f"PARSE - MaxWP={self.max_willpower} MaxBlood={self.max_blood} BPT={self.blood_per_turn}"))

        # Derangements
        self.derangments = [self.get_derangement_value(f"AM{c}") for c in range(107, 128)]

        # Combo Disciplines
        self.combo_disciplines = [self.get_combo_discipline(f"C{c}") for c in range(132, 295)]
        self.combo_disciplines = [c for c in self.combo_disciplines if c]

        # Rituals
        self.rituals = [self.get_ritual(f"U{c}") for c in range(132, 295)]
        self.rituals = [r for r in self.rituals if r and r.get("name")]

        # Magic Paths
        self.magic_paths = [self.get_magic_path(f"AM{c}") for c in range(132, 295)]
        self.magic_paths = [p for p in self.magic_paths if p and p.get("name")]

        logger.info(self._ctx("PARSE - Completed parsing core blocks; fetching XP log next"))
        # Fetch XP Log (also sets curr_xp / total_xp)
        self.fetch_xp_log()
        logger.info(self._ctx("PARSE - All parsing complete"))

    # ----------------------------------------------------------------------------------
    # Utility / Presentation
    # ----------------------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-safe dict representation of the character automatically."""
        result = {}
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                continue
            if hasattr(value, "to_dict"):
                result[key] = value.to_dict()
            else:
                result[key] = value
        return result

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

        def format_list(title: str, items: List[str], indent: int = 2) -> List[str]:
            section = [f"{title}:"]
            if not items:
                section.append(" " * indent + "None")
                return section
            for i in items:
                section.append(" " * indent + str(i))
            return section

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

    # ----------------------------------------------------------------------------------
    # Simple mutators
    # ----------------------------------------------------------------------------------

    def reset_temp(self):
        """Reset temporary values like current willpower and blood"""
        logger.info(self._ctx("STATE - Resetting temp pools"))
        self.curr_willpower = self.max_willpower
        self.curr_blood = self.max_blood

    def reset_willpower(self):
        logger.info(self._ctx("STATE - Resetting current willpower to max"))
        self.curr_willpower = self.max_willpower

    # ----------------------------------------------------------------------------------
    # Sheets write helpers
    # ----------------------------------------------------------------------------------

    def write_dta_log(self, ctx: discord.Interaction):
        """
        Write all entries in self.dta_log to the 'XP & Downtime Logs' worksheet.

        - Clears rows 12–199 (AF:BB) before writing new data.
        - AF = timestamp (DD-MM-YYYY)
        - AJ = gained (positive delta, number only)
        - AM = spent (negative delta, number only)
        - AP = comment
        - BB = Discord username (resolved via guild member, fallback to 'N/A')
        """
        if not self.dta_log:
            logger.info(self._ctx("DTA - No DTA log entries to write"))
            return

        logger.info(self._ctx(f"DTA - Preparing to write {len(self.dta_log)} entries to sheet"))

        try:
            client = get_client()
            spreadsheet = client.open_by_url(self.SHEET_URL)
            worksheet = spreadsheet.worksheet("XP & Downtime Logs")
        except Exception as e:
            logger.exception(self._ctx(f"DTA - Failed to open sheet: {e}"))
            raise

        # Clear existing range
        clear_range = "AF12:BB199"
        try:
            worksheet.batch_clear([clear_range])
            logger.info(self._ctx(f"DTA - Cleared existing log range {clear_range}"))
        except Exception as e:
            logger.exception(self._ctx(f"DTA - Failed to clear range {clear_range}: {e}"))
            raise

        start_row = 12
        all_row_values = []

        for entry in self.dta_log:
            # Timestamp
            raw_ts = entry.get("timestamp")
            try:
                ts_dt = datetime.fromisoformat(raw_ts)
            except (TypeError, ValueError):
                ts_dt = datetime.utcnow()
            ts = ts_dt.strftime("%d-%m-%Y")

            # Parse delta sign/value
            raw_delta = str(entry.get("delta", "0")).strip()
            sign = 1
            if raw_delta.startswith("+"):
                raw_delta = raw_delta[1:]
            elif raw_delta.startswith("-"):
                sign = -1
                raw_delta = raw_delta[1:]

            try:
                delta_value = float(raw_delta) if "." in raw_delta else int(raw_delta)
            except ValueError:
                delta_value = 0

            sheet_value = abs(delta_value)
            comment = entry.get("reasoning", "")

            # Resolve Discord member => username
            user_id = entry.get("user")
            username = "N/A"
            try:
                member = ctx.guild.get_member(int(user_id)) if ctx and ctx.guild else None
                if member:
                    username = member.name
            except Exception as e:
                logger.warning(self._ctx(f"DTA - Failed to resolve member for ID {user_id}: {e}"))

            # Fill row (AF:BB → 23 columns)
            row_values = [""] * 23
            row_values[0] = ts  # AF
            if sign >= 0:
                row_values[4] = sheet_value  # AJ (Gained)
            else:
                row_values[7] = sheet_value  # AM (Spent)
            row_values[10] = comment  # AP
            row_values[22] = username  # BB

            all_row_values.append(row_values)

        # Batch update
        if all_row_values:
            end_row = start_row + len(all_row_values) - 1
            update_range = f"AF{start_row}:BB{end_row}"
            try:
                worksheet.update(update_range, all_row_values)
                logger.info(self._ctx(f"DTA - Wrote {len(all_row_values)} entries to {update_range}"))
            except Exception as e:
                logger.exception(self._ctx(f"DTA - Failed to update range {update_range}: {e}"))
                raise
        else:
            logger.info(self._ctx("DTA - No rows to write after processing"))

    def write_xp_log(self, ctx: discord.Interaction):
        """
        Write XP log entries to 'XP & Downtime Logs' tab.

        Columns (row 12+):
          B  = date (string, e.g. '12/10/2025' or '12/10/2025 - 18/10/2025')
          F  = gained (positive delta, number)
          I  = spent (negative delta, number)
          L  = comment (same as date block string)
          X  = storyteller (Discord username)
        """
        logs: List[Dict] = getattr(self, "xp_log", []) or []
        if not logs:
            logger.info("XP - write_xp_log: no entries to write.")
            return

        try:
            client = get_client()
            spreadsheet = client.open_by_url(self.SHEET_URL)
            ws = spreadsheet.worksheet("XP & Downtime Logs")
        except Exception as e:
            logger.exception(f"XP - write_xp_log: failed to open sheet: {e}")
            return

        # We will clear a conservative block and rewrite.
        # B..X spans 23 columns (B is col 2, X is col 24).
        clear_range = "B12:X199"
        try:
            ws.batch_clear([clear_range])
        except Exception as e:
            logger.warning(f"XP - write_xp_log: failed to clear range {clear_range}: {e}")

        # Prepare rows
        start_row = 12
        rows = []
        for entry in logs:
            # pad to 23 columns (B..X) and fill in the mapped columns
            # We only care about B,F,I,L,X.
            # We'll build an array of 23 cells initialized to "".
            row = [""] * 23

            date_str = entry.get("date") or ""
            comment = entry.get("comment") or date_str
            storyteller = entry.get("storyteller") or "N/A"

            # B (index 0)
            row[0] = date_str

            # Delta: positive goes to F (index 4), negative goes to I (index 7)
            delta = entry.get("delta", 0) or 0
            try:
                d = float(delta)
            except Exception:
                d = 0.0

            if d >= 0:
                row[4] = d
            else:
                row[7] = abs(d)

            # L (index 10): comment
            row[10] = comment

            # X (index 23): storyteller (Discord username)
            row[23] = storyteller

            rows.append(row)

        if rows:
            end_row = start_row + len(rows) - 1
            rng = f"B{start_row}:X{end_row}"
            try:
                ws.update(rng, rows)
                logger.info(f"XP - write_xp_log: wrote {len(rows)} rows to {rng}")
            except Exception as e:
                logger.exception(f"XP - write_xp_log: failed to update {rng}: {e}")

    def fetch_xp_log(self):
        """
        Fetch and parse XP log from 'XP & Downtime Logs', filling:
          - self.curr_xp
          - self.total_xp
          - self.xp_log (list of {date, delta, comment, storyteller})

        Reads B12:AB(last_row-5) to get a stable slice regardless of "used rows".
        """
        logger.info("XP - Fetching XP log from sheet")
        try:
            client = get_client()
            ss = client.open_by_url(self.SHEET_URL)
            ws = ss.worksheet("XP & Downtime Logs")
        except Exception as e:
            logger.exception(f"XP - fetch_xp_log: failed to open sheet: {e}")
            self.xp_log = []
            self.curr_xp = 0
            self.total_xp = 0
            return

        # Get current and total XP (same indices you used)
        try:
            all_values = ws.get_all_values()
        except Exception as e:
            logger.exception(f"XP - fetch_xp_log: get_all_values failed: {e}")
            self.xp_log = []
            self.curr_xp = 0
            self.total_xp = 0
            return

        try:
            self.curr_xp = all_values[5][24]  # row 6, col AI (0-based [5][24])
        except Exception:
            self.curr_xp = 0
        try:
            self.total_xp = all_values[5][7]  # row 6, col H (0-based [5][7])
        except Exception:
            self.total_xp = 0

        # B12:AB(last_row-5)
        total_sheet_rows = ws.row_count
        start_row = 12
        end_row = max(start_row, total_sheet_rows - 5)
        rng = f"B{start_row}:AB{end_row}"

        try:
            data_rows = ws.get(rng)  # includes blanks as empty cells
        except Exception as e:
            logger.exception(f"XP - fetch_xp_log: failed to get {rng}: {e}")
            self.xp_log = []
            return

        xp_logs: List[Dict] = []
        for row in data_rows:
            # Pad to 28 columns (B..AB is 28 cols)
            row = list(row) + [None] * max(0, 28 - len(row))

            # Column mapping relative to B:
            # B(0)=date, F(4)=increase, I(7)=decrease, L(10)=comment, X(23)=storyteller
            date = row[0]
            increase = row[4] or 0
            decrease = row[7] or 0
            comment = row[10]
            storyteller = row[23]

            try:
                inc = float(increase) if increase not in (None, "") else 0.0
            except Exception:
                inc = 0.0
            try:
                dec = float(decrease) if decrease not in (None, "") else 0.0
            except Exception:
                dec = 0.0

            delta = inc - dec

            # ignore completely empty rows
            if not any([date, comment, inc, dec]):
                continue

            xp_logs.append(
                {
                    "date": date,
                    "delta": delta,
                    "comment": comment,
                    "storyteller": storyteller,
                }
            )

        logger.info(f"XP - Parsed {len(xp_logs)} XP entries (curr_xp={self.curr_xp}, total_xp={self.total_xp})")
        self.xp_log = xp_logs