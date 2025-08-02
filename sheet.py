import gspread
from google.oauth2.service_account import Credentials
from typing import List, Optional, Dict

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SERVICE_ACCOUNT_FILE = "credentials.json"

def get_client() -> gspread.Client:
    try:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"[ERROR] Failed to load credentials: {e}")
        print("🔑 Please regenerate your service account key (credentials.json).")
        raise

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
    
    TALENT_RANGES = {
        "alertness": "J46:N46",
        "athletics": "J47:N47",
        "awareness": "J48:N48",
        "brawl": "J49:N49",
        "empathy": "J50:N50",
        "expression": "J51:N51",
        "intimidation": "J52:N52",
        "leadership": "J53:N53",
        "streetwise": "J54:N54",
        "subterfuge": "J55:N55"
    }
    
    SKILL_RANGES = {
        "animal_ken": "V46:Z46",
        "craft": "V47:Z47",
        "drive": "V48:Z48",
        "etiquette": "V49:Z49",
        "firearms": "V50:Z50",
        "larceny": "V51:Z51",
        "melee": "V52:Z52",
        "performance": "V53:Z53",
        "stealth": "V54:Z54",
        "survival": "V55:Z55"
    }
    
    KNOWLEDGE_RANGES = {
        "academics": "AH46:AL46",
        "computer": "AH47:AL47",
        "finance": "AH48:AL48",
        "investigation": "AH49:AL49",
        "law": "AH50:AL50",
        "medicine": "AH51:AL51",
        "occult": "AH52:AL52",
        "politics": "AH53:AL53",
        "science": "AH54:AL54",
        "technology": "AH55:AL55",
    }

    BASIC_INFO_CELLS = [
        "E11", "T11", "E14", "T14",
        "E17", "T17", "E19", "T19",
        "O26", "O27", "O28"
    ]
    
    SPECIALTY_COLUMNS = [
        ("AO", "AS"),
        ("AX", "BB")
    ]
    START_ROW = 34
    END_ROW = 60

    def __init__(self, worksheet: gspread.Worksheet):
        print("[DEBUG] Initializing Character object...")
        self.worksheet = worksheet

        print("[DEBUG] Reading basic info in batch...")
        basic_values = worksheet.batch_get(self.BASIC_INFO_CELLS)
        (
            self.name,
            self.alt_name,
            self.visible_age,
            self.actual_age,
            self.nature,
            self.demeanor,
            self.personality_nature,
            self.personality_demeanor,
            self.clan,
            self.sect,
            self.generation
        ) = [cells[0][0] if cells and cells[0] else "" for cells in basic_values]

        print("[DEBUG] Reading attributes, talents, skills, knowledges in batches...")
        self.attributes = self._parse_multiple(self.ATTR_RANGES, mod=1)
        self.talents = self._parse_multiple(self.TALENT_RANGES)
        self.skills = self._parse_multiple(self.SKILL_RANGES)
        self.knowledges = self._parse_multiple(self.KNOWLEDGE_RANGES)

        print("[DEBUG] Reading specialties...")
        self.specialties = self._parse_specialties()

    def _parse_multiple(self, ranges_dict: Dict[str, str], mod: int = 0) -> Dict[str, int]:
        ranges = list(ranges_dict.values())
        results = self.worksheet.batch_get(ranges)
        parsed = {}
        for (name, _), cells in zip(ranges_dict.items(), results):
            flat_values = [val for row in cells for val in row if val]
            parsed[name] = len(flat_values) + mod
        return parsed

    def _parse_specialties(self) -> Dict[str, List[str]]:
        """Fetches all specialties for each trait across both column pairs and rows."""
        ranges = []
        for attr_col, spec_col in self.SPECIALTY_COLUMNS:
            ranges.append(f"{attr_col}{self.START_ROW}:{attr_col}{self.END_ROW}")
            ranges.append(f"{spec_col}{self.START_ROW}:{spec_col}{self.END_ROW}")

        results = self.worksheet.batch_get(ranges)
        specialty_lookup = {}
        i = 0
        for attr_col, spec_col in self.SPECIALTY_COLUMNS:
            attr_vals = [row[0] if row else "" for row in results[i]]
            spec_vals = [row[0] if row else "" for row in results[i + 1]]
            for trait, spec in zip(attr_vals, spec_vals):
                if trait and spec:
                    key = trait.strip().lower()
                    if key not in specialty_lookup:
                        specialty_lookup[key] = []
                    specialty_lookup[key].append(spec.strip())
            i += 2
        return specialty_lookup


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

        print("\nAttributes:")
        for attr, score in self.attributes.items():
            name = attr.title()
            specialties = self.specialties.get(name.lower(), [])
            if specialties:
                print(f"{name} [{', '.join(specialties)}]: {score}")
            else:
                print(f"{name}: {score}")

        print("\nTalents:")
        for talent, score in self.talents.items():
            name = talent.replace('_', ' ').title()
            specialties = self.specialties.get(name.lower(), [])
            if specialties:
                print(f"{name} [{', '.join(specialties)}]: {score}")
            else:
                print(f"{name}: {score}")

        print("\nSkills:")
        for skill, score in self.skills.items():
            name = skill.replace('_', ' ').title()
            specialties = self.specialties.get(name.lower(), [])
            if specialties:
                print(f"{name} [{', '.join(specialties)}]: {score}")
            else:
                print(f"{name}: {score}")

        print("\nKnowledges:")
        for knowledge, score in self.knowledges.items():
            name = knowledge.replace('_', ' ').title()
            specialties = self.specialties.get(name.lower(), [])
            if specialties:
                print(f"{name} [{', '.join(specialties)}]: {score}")
            else:
                print(f"{name}: {score}")


    def edit_cell(self, cell: str, value: str):
        print(f"[DEBUG] Updating cell {cell} to '{value}'")
        self.worksheet.update_acell(cell, value)
        print(f"[DEBUG] Cell {cell} successfully updated.")

if __name__ == "__main__":
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1C4MClgF7B02PI9Vq16ggqYxZ8CQuNMWNMaoKGsMAKdE/edit?usp=sharing"
    
    client = get_client()
    spreadsheet = client.open_by_url(SHEET_URL)
    worksheet = spreadsheet.get_worksheet(0)

    character = Character(worksheet)
    character.display()
