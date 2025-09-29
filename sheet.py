import logging
from lib.character import Character
from lib.database_loader import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Change to INFO for debugging
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("character_debug.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    SHEET_URL = (
        "https://docs.google.com/spreadsheets/d/"
        "17G7IDHWXJlXqZ5p9Ow-Uh5MSPpXNX9GRXeO8auYSbKk/"
        "edit?gid=1568844995#gid=1568844995"
    )
    
    init_db()

    # First time: fetch from Sheets
    #char = Character(SHEET_URL=SHEET_URL, user_id="user123")
    #print(char)
    #char.save_parsed()  # Store parsed JSON only

    # Later: reload without hitting Sheets
    loaded = Character.load_parsed("f3fa8a51-7d8f-4b95-9fe3-e6e81647b3b3", "user123")
    print("Loaded from DB:", loaded.name, loaded.clan, loaded.generation)
    loaded.refetch_data()
    print(loaded)