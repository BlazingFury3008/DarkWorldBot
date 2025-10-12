# Installing
To install the bot, a `.env` file is required in the following format
```env
DISCORD_KEY=""
ROLES=""
BASE_SHEET=""
```
DISCORD KEY is the key for the Bot to run
ROLES are the roles allowed to use Storyteller commands 'st_commands.py'
BASE_SHEET is the base variant of the sheet used in The Dark World - South Florida

Run `venv.bat` which will create a Python Virtual Enviroment and install the neccessary dependancies, then run `venv/scripts/activate` before finally running `run.bat`

# Sectional Commands
## Character
### Init
*Params: URL - The URL to the sheet where the character is stored*
This command takes the URL of sheet, creates a Character Object which is stored in the database 'characters.py'