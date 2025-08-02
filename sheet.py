import gspread
from google.oauth2.service_account import Credentials
from typing import List, Optional, Dict

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SERVICE_ACCOUNT_FILE = "credentials.json"

def get_client() -> gspread.Client:
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

# -------------------------------
# CHARACTER CLASS
# -------------------------------
class Character:
    ATTR_RANGES = {
        "strength": "J36:N36",
        "dexterity": "J37:N37",
        "stamina": "J38:N38",
        "charisma": "V36:Z36",
        "manipulation": "V37:Z37",
        "appearance": "V38:Z38",
        "perception": "AH36:AL36",
        "intelligence": "AH37:AL37",
        "wits": "AH38:AL38"
    }

    def __init__(self, worksheet: gspread.Worksheet):
        print("[DEBUG] Initializing Character object...")
        self.worksheet = worksheet
        
        # Basic Info
        self.name = self._read_cell("E11")
        self.alt_name = self._read_cell("T11")
        self.visible_age = self._read_cell("E14")
        self.actual_age = self._read_cell("T14")
        self.nature = self._read_cell("E17")
        self.demeanor = self._read_cell("T17")
        self.personality_nature = self._read_cell("E19")
        self.personality_demeanor = self._read_cell("T19")
        
        # Attributes (+1 bonus)
        print("[DEBUG] Reading all attributes...")
        self.attributes = self._parse_all_attributes()
        print(f"[DEBUG] Attributes loaded: {self.attributes}")

    def _read_cell(self, cell: str) -> Optional[str]:
        value = self.worksheet.acell(cell).value
        print(f"[DEBUG] Read cell {cell}: {value}")
        return value

    def _read_range(self, cell_range: str) -> List[List[str]]:
        values = self.worksheet.get(cell_range)
        print(f"[DEBUG] Read range {cell_range}: {values}")
        return values

    def _parse_attribute(self, cell_range: str) -> int:
        raw_values = self._read_range(cell_range)
        flat_values = [val for sublist in raw_values for val in sublist if val]
        score = len(flat_values) + 1
        print(f"[DEBUG] Calculated score for {cell_range} -> {score}")
        return score

    def _parse_all_attributes(self) -> Dict[str, int]:
        return {attr_name: self._parse_attribute(cell_range) 
                for attr_name, cell_range in self.ATTR_RANGES.items()}

    def display(self):
        print("📜 Character Sheet Data")
        print(f"Name: {self.name}")
        print(f"Alternative Name: {self.alt_name}")
        print(f"Visible Age: {self.visible_age}")
        print(f"Actual Age: {self.actual_age}")
        print(f"Nature: {self.nature}")
        print(f"Demeanor: {self.demeanor}")
        print(f"Personality (Nature): {self.personality_nature}")
        print(f"Personality (Demeanor): {self.personality_demeanor}")
        
        print("\n💪 Attributes (+1 bonus applied):")
        for attr, score in self.attributes.items():
            print(f"{attr.title()}: {score}")

# -------------------------------
# MAIN EXECUTION
# -------------------------------
if __name__ == "__main__":
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1C4MClgF7B02PI9Vq16ggqYxZ8CQuNMWNMaoKGsMAKdE/edit?usp=sharing"
    
    client = get_client()
    spreadsheet = client.open_by_url(SHEET_URL)
    worksheet = spreadsheet.get_worksheet(0)

    character = Character(worksheet)
    character.display()
