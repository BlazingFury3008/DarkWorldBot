import gspread
import logging
from google.oauth2.service_account import Credentials
from typing import List, Optional, Dict

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
SERVICE_ACCOUNT_FILE = "credentials.json"

logging.basicConfig(
    level=logging.ERROR,  # Change to INFO or ERROR in production
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("character_debug.log"),  # Log to file
        logging.StreamHandler()                      # Also log to console
    ]
)
logger = logging.getLogger(__name__)

def get_client() -> gspread.Client:
    try:
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"[ERROR] Failed to load credentials: {e}")
        logger.error("Please regenerate your service account key (credentials.json).")
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
    
    VIRTUE_CELLS = [
            "X65", ("AG65:AK65"),
            "X66", ("AG66:AK66"),
            "X67", ("AG67:AK67"),
        ]

    def __init__(self, worksheet: gspread.Worksheet):
        logger.debug("Initializing Character object...")
        self.worksheet = worksheet
        

        logger.debug("Reading basic info in batch...")
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

        logger.debug("Reading attributes, talents, skills, knowledges in batches...")
        self.attributes = self._parse_multiple(self.ATTR_RANGES, mod=1)
        self.talents = self._parse_multiple(self.TALENT_RANGES)
        self.skills = self._parse_multiple(self.SKILL_RANGES)
        self.knowledges = self._parse_multiple(self.KNOWLEDGE_RANGES)
        self.virtues = self._parse_virtues()
        self.perm_willpower, self.temp_willpower = self._parse_willpower()
        self.perm_blood, self.temp_blood = self._parse_bloodpool()

        logger.debug("Reading specialties...")
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
    
    def _parse_virtues(self):
        """Parses virtues, getting text for names and counting length for value cells."""
        virtue_values = self.worksheet.batch_get(self.VIRTUE_CELLS)

        virtues = {}
        for i in range(0, len(virtue_values), 2):
            # Name cell (e.g., "Conscience")
            name = virtue_values[i][0][0] if virtue_values[i] and virtue_values[i][0] else ""

            # Value cell (e.g., dots ●●●), count non-empty entries
            value_cells = virtue_values[i + 1] if i + 1 < len(virtue_values) else []
            flat_values = [val for row in value_cells for val in row if val]
            virtues[name] = len(flat_values)

        return virtues
    
    def _parse_willpower(self):
        will = self.worksheet.batch_get(["Z79:AI79", "Z80:AI80"])
        return len(will[0][0]), len(will[1][0])
    
    def _parse_bloodpool(self):
        perm_blood = (13 - int(self.generation)) + 10
        temp_blood = len(self.worksheet.get("AB85:AK87")[0])
        
        return perm_blood, temp_blood
    
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
                
        print(f"\nVirtues: {self.virtues}")
        print(f"Willpower: {self.temp_willpower}/{self.perm_willpower}" )
        print(f"Bloodpool: {self.temp_blood}/{self.perm_blood}")


    def edit_cell(self, cell: str, value: str):
        logger.debug(f"Updating cell {cell} to '{value}'")
        self.worksheet.update_acell(cell, value)
        logger.debug(f"Cell {cell} successfully updated.")
        
            
    def reset_willpower(self):
        """
        Resets the character's willpower dots from Z80 to AI80 (10 cells inclusive).
        Fills with 'b' up to perm_willpower and clears the rest using a batch update.
        """
        try:
            willpower_columns = ["Z", "AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH", "AI"]
            row = 80
            
            updates = []
            for i, col in enumerate(willpower_columns):
                cell = f"{col}{row}"
                value = "b" if i < self.perm_willpower else ""
                updates.append({"range": cell, "values": [[value]]})
                logger.debug(f"Marked {cell} -> '{value}'")

            # Perform a single batch update
            self.worksheet.batch_update(updates)

            self.temp_willpower = self.perm_willpower
            logger.debug(f"Willpower successfully reset to {self.perm_willpower} dots")

            return self.temp_willpower, self.perm_willpower

        except Exception as e:
            logger.error(f"Failed to reset willpower: {e}")
            return self.temp_willpower, self.perm_willpower
            
    def adjust_willpower(self, amount: int):
        """
        Adjusts temporary willpower by a positive or negative amount.
        - Positive amount → adds willpower from left to right.
        - Negative amount → spends willpower from right to left.
        Updates the sheet and internal state.
        """
        try:
            willpower_columns = ["Z", "AA", "AB", "AC", "AD", "AE", "AF", "AG", "AH", "AI"]
            row = 80

            # Get current state
            sheet_data = self.worksheet.batch_get([f"Z{row}:AI{row}"])
            cells = sheet_data[0][0] if sheet_data and sheet_data[0] else []

            # Pad cells to always have 10 values
            while len(cells) < len(willpower_columns):
                cells.append("")

            logger.debug(f"Current willpower cells: {cells}")

            # Count filled cells
            filled_indexes = [i for i, val in enumerate(cells) if val.strip() != ""]
            empty_indexes = [i for i, val in enumerate(cells) if val.strip() == ""]

            updates = []

            if amount < 0:  # Spend willpower
                spend = abs(amount)
                if spend > len(filled_indexes):
                    logger.error("Not enough willpower to spend")
                    return self.temp_willpower, self.perm_willpower

                for idx in reversed(filled_indexes[-spend:]):
                    cell = f"{willpower_columns[idx]}{row}"
                    updates.append({"range": cell, "values": [[""]]})
                    logger.debug(f"Marked to clear: {cell}")

                self.temp_willpower -= spend

            elif amount > 0:  # Add willpower
                add = amount
                if self.temp_willpower >= self.perm_willpower:
                    logger.info("Willpower already full")
                    return self.temp_willpower, self.perm_willpower

                if self.temp_willpower + add > self.perm_willpower:
                    add = self.perm_willpower - self.temp_willpower
                    logger.warning(f"Adjusted amount to {add} to not exceed permanent willpower")

                if len(empty_indexes) < add:
                    logger.warning("Not enough empty cells; adjusting amount")
                    add = len(empty_indexes)

                for idx in empty_indexes[:add]:
                    cell = f"{willpower_columns[idx]}{row}"
                    updates.append({"range": cell, "values": [["b"]]})
                    logger.debug(f"Marked to fill: {cell}")

                self.temp_willpower += add

            else:
                logger.info("Adjustment value is 0; nothing to do")
                return self.temp_willpower, self.perm_willpower

            # Perform batch update
            if updates:
                self.worksheet.batch_update(updates)

            logger.debug(f"Willpower successfully adjusted to {self.temp_willpower}/{self.perm_willpower}")
            return self.temp_willpower, self.perm_willpower

        except Exception as e:
            logger.error(f"Failed to adjust willpower: {e}")
            return self.temp_willpower, self.perm_willpower


    def reset_bloodpool(self):
        """
        Resets the character's blood pool dots from AB85 to AK87 (3 rows).
        Fills with 'b' up to the permanent bloodpool size (self.perm_blood)
        and clears the rest.
        """
        try:
            # Define grid
            blood_columns = ["AB", "AC", "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK"]
            row_indices = [85, 86, 87]
            updates = []
            dot_index = 0
            total_cells = len(blood_columns) * len(row_indices)

            if self.perm_blood > total_cells:
                logger.warning(f"perm_bloodpool ({self.perm_blood}) exceeds grid size ({total_cells}).")
                self.perm_blood = total_cells

            # Fill up to permanent blood dots
            for row in row_indices:
                for col in blood_columns:
                    value = "b" if dot_index < self.perm_blood else ""
                    updates.append({"range": f"{col}{row}", "values": [[value]]})
                    dot_index += 1

            # Batch update
            self.worksheet.batch_update(updates)

            # Update temp bloodpool to match permanent
            self.temp_blood = self.perm_blood

            logger.debug(f"Blood pool successfully reset to {self.perm_blood} dots")
            return self.temp_blood, self.perm_blood

        except Exception as e:
            logger.error(f"Failed to reset blood pool: {e}")
            return getattr(self, "temp_bloodpool", 0), getattr(self, "perm_bloodpool", 0)
        
    def adjust_blood(self, amount: int):
        """
        Adjusts the blood pool by a positive or negative amount.
        - Positive amount → adds blood (top-left to bottom-right).
        - Negative amount → spends blood (bottom-right to top-left).
        Uses batch_update for efficiency and respects perm_blood limit.
        """
        try:
            blood_columns = ["AB", "AC", "AD", "AE", "AF", "AG", "AH", "AI", "AJ", "AK"]
            row_indices = [85, 86, 87]

            # Read current state
            all_rows = self.worksheet.batch_get([f"AB{row_indices[0]}:AK{row_indices[-1]}"])[0]
            logger.debug(f"Current blood pool cells: {all_rows}")

            # Flatten cells and prepare indexes
            filled_positions = []
            empty_positions = []

            for r_idx, row in enumerate(all_rows):
                row += [""] * (len(blood_columns) - len(row))  # Pad row
                for c_idx, val in enumerate(row):
                    cell = f"{blood_columns[c_idx]}{row_indices[r_idx]}"
                    if val.strip() != "":
                        filled_positions.append(cell)
                    else:
                        empty_positions.append(cell)

            logger.debug(f"Filled cells: {filled_positions}")
            logger.debug(f"Empty cells: {empty_positions}")

            updates = []

            # Handle spending (negative value)
            if amount < 0:
                spend = abs(amount)
                if spend > len(filled_positions):
                    logger.error("Not enough blood to spend")
                    return self.temp_blood, self.perm_blood

                # Sort filled cells bottom-right → top-left
                filled_positions_sorted = sorted(
                    filled_positions,
                    key=lambda cell: (
                        -row_indices.index(int(cell[2:])),
                        -blood_columns.index(cell[:2]) if len(cell) == 4 else -blood_columns.index(cell[:1])
                    )
                )

                for cell in filled_positions_sorted[:spend]:
                    updates.append({"range": cell, "values": [[""]]})
                    logger.debug(f"Marked to clear: {cell}")

                self.temp_blood -= spend

            # Handle adding (positive value)
            elif amount > 0:
                add = amount
                if self.temp_blood >= self.perm_blood:
                    logger.info("Blood pool already full")
                    return self.temp_blood, self.perm_blood

                if self.temp_blood + add > self.perm_blood:
                    add = self.perm_blood - self.temp_blood
                    logger.warning(f"Adjusted amount to {add} to not exceed permanent blood capacity")

                if len(empty_positions) < add:
                    logger.warning("Not enough empty cells; adjusting amount")
                    add = len(empty_positions)

                # Sort empty cells top-left → bottom-right
                empty_positions_sorted = sorted(
                    empty_positions,
                    key=lambda cell: (
                        row_indices.index(int(cell[2:])),
                        blood_columns.index(cell[:2]) if len(cell) == 4 else blood_columns.index(cell[:1])
                    )
                )

                for cell in empty_positions_sorted[:add]:
                    updates.append({"range": cell, "values": [["b"]]})
                    logger.debug(f"Marked to fill: {cell}")

                self.temp_blood += add

            else:
                logger.info("Adjustment value is 0; nothing to do")
                return self.temp_blood, self.perm_blood

            # Batch update
            if updates:
                self.worksheet.batch_update(updates)

            logger.debug(f"Blood pool successfully adjusted to {self.temp_blood}/{self.perm_blood}")
            return self.temp_blood, self.perm_blood

        except Exception as e:
            logger.error(f"Failed to adjust blood: {e}")
            return self.temp_blood, self.perm_blood

        
if __name__ == "__main__":
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1C4MClgF7B02PI9Vq16ggqYxZ8CQuNMWNMaoKGsMAKdE/edit?usp=sharing"
    
    client = get_client()
    spreadsheet = client.open_by_url(SHEET_URL)
    worksheet = spreadsheet.get_worksheet(0)

    character = Character(worksheet)
    #character.display()
    character.reset_willpower()
    character.adjust_willpower(-4)
    character.adjust_willpower(3)
    character.reset_bloodpool()
    character.adjust_blood(-6)
    character.adjust_blood(3)
    character.display()