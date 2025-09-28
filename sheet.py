import gspread
import logging
import os
import pickle
import re
from google.oauth2.service_account import Credentials
from typing import Dict

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SERVICE_ACCOUNT_FILE = "credentials.json"
CACHE_FILE = "character_cache.pkl"

logging.basicConfig(
    level=logging.ERROR,  # Change to INFO in production
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("character_debug.log"),  # Log to file
        logging.StreamHandler()                      # Also log to console
    ]
)
logger = logging.getLogger(__name__)


def get_client() -> gspread.Client:
    try:
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"[ERROR] Failed to load credentials: {e}")
        raise


def save_cache(data: Dict, filename: str = CACHE_FILE):
    with open(filename, "wb") as f:
        pickle.dump(data, f)


def load_cache(filename: str = CACHE_FILE):
    if os.path.exists(filename):
        with open(filename, "rb") as f:
            return pickle.load(f)
    return None


class Character:

    def __init__(self, SHEET_URL: str, use_cache: bool = True):
        cached = load_cache() if use_cache else None

        if cached:
            logger.info("Loaded worksheet data from local cache")
            self.sheet_values = cached["sheet_values"]
        else:
            logger.info("Fetching worksheet from Google Sheets")
            client = get_client()
            spreadsheet = client.open_by_url(SHEET_URL)
            worksheet = spreadsheet.get_worksheet_by_id(0)

            # Fetch the whole sheet at once (1 API call)
            self.sheet_values = worksheet.get_all_values()

            # Save to cache
            save_cache({"sheet_values": self.sheet_values})

        # Load fields
        self.name = self.get_val_from_cell("AS3")
        self.player_name = self.get_val_from_cell("AS5")
        self.concept = self.get_val_from_cell("AS8")
        self.nature = self.get_val_from_cell("AS9")
        self.demeanor = self.get_val_from_cell("AS10")
        self.ranking = self.get_val_from_cell("AS12")
        self.generation = self.get_val_from_cell("AS13")
        self.kindred_time = self.get_val_from_cell("AS14")
        self.age = self.get_val_from_cell("AS15")
        self.sect = self.get_val_from_cell("AS17")
        self.clan = self.get_val_from_cell("AS20")
        self.bane = self.get_val_from_cell("AS23")

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

    def get_val_from_cell(self, cell: str) -> str:
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            return self.sheet_values[row - 1][col - 1]
        except IndexError:
            return None

    def get_trait(self, cell: str) -> Dict:
        row, col = gspread.utils.a1_to_rowcol(cell)
        try:
            name = self.sheet_values[row - 1][col - 1]
        except IndexError:
            return {"name": None, "value": 0, "specs": None}

        # Count filled dots from col+6 to col+15
        values = []
        for c in range(col + 6, col + 16):
            try:
                values.append(self.sheet_values[row - 1][c - 1])
            except IndexError:
                break
        value_count = sum(1 for v in values if v not in (None, ""))

        # Specialties row+1, col+4
        try:
            specs = self.sheet_values[row][col + 3]
        except IndexError:
            specs = None

        return {"name": name, "value": value_count, "specs": specs}

    def display_char(self):
        print(f"""*{self.concept}*
Name: {self.name}
Player: {self.player_name}

Clan: {self.clan}
Generation: {self.generation} ({self.ranking})
Sect: {self.sect}

Age: {self.age} ({self.kindred_time} Years since embrace)
""")


if __name__ == "__main__":
    SHEET_URL = "https://docs.google.com/spreadsheets/d/17G7IDHWXJlXqZ5p9Ow-Uh5MSPpXNX9GRXeO8auYSbKk/edit?gid=1568844995#gid=1568844995"

    char = Character(SHEET_URL, use_cache=True)
    char.display_char()

    for trait in char.attributes:
        print(trait)

    for cat, traits in char.abilities.items():
        print(f"---- {cat} ----")
        for trait in traits:
            print(trait)
