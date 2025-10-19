import discord
import ast
from discord import app_commands

from dotenv import dotenv_values
config = dotenv_values(".env")

# ---------------------------
# MACRO HELP EMBED FUNCTION
# ---------------------------
def get_macro_help_embed() -> discord.Embed:
    """Return an embed explaining how to use macros."""
    embed = discord.Embed(
        title="Macro Help",
        description=(
            "Macros allow you to define reusable dice expressions for a character. "
            "Once defined, they can be listed, updated, or deleted."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="Basic Syntax",
        value=(
            "`<name> = <expression>`\n"
            "Expressions may include attributes, abilities, disciplines, numbers, "
            "and optional [Specializations].\n\n"
            "**Examples:**\n"
            "`SwordAttack = Dexterity+Melee[Swords]`\n"
            "`Fireball = Intelligence+Occult+3`\n"
            "`StealthCheck = Dexterity+Stealth`\n"
        ),
        inline=False
    )

    embed.add_field(
        name="Valid Tokens",
        value=(
            "- Attributes and Abilities: `Dexterity`, `Melee[Swords]`\n"
            "- Disciplines and Backgrounds also allowed\n"
            "- Numbers: `+3`, `-2` etc.\n"
            "- Operators: `+` and `-` between tokens\n\n"
            "The pattern must alternate between tokens and operators.\n"
            "For example: `Dexterity+Melee[Swords]+2` is valid, "
            "but `Dexterity++Melee` is not."
        ),
        inline=False
    )

    embed.add_field(
        name="Commands",
        value=(
            "`/macro new` – Create a new macro\n"
            "`/macro update` – Update an existing macro\n"
            "`/macro list` – View all macros and their dicepool values\n"
            "`/macro delete` – Delete a macro\n"
            "`/macro help` – Show this help"
        ),
        inline=False
    )

    embed.add_field(
        name="Validation Steps",
        value=(
            "1. **Syntax Check:** Ensures the macro is in the correct format.\n"
            "2. **Resolution Check:** Ensures all tokens in the expression exist for your character."
        ),
        inline=False
    )

    return embed


# ---------------------------
# ROLL HELP EMBED FUNCTION
# ---------------------------
def get_roll_help_embed() -> discord.Embed:
    """Return an embed explaining how to use the /roll command."""
    embed = discord.Embed(
        title="Roll Command Help",
        description=(
            "The `/roll` command allows you to roll dice pools using either **raw expressions** "
            "or **predefined macros**."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="Basic Syntax",
        value=(
            "`/roll name:<Character> roll_str:<Expression or Macro> difficulty:<Number>`\n\n"
            "**Examples:**\n"
            "`/roll name:Aldric roll_str:Dexterity+Melee difficulty:6`\n"
            "`/roll name:Aldric roll_str:SwordAttack difficulty:6`\n"
            "`/roll name:Aldric roll_str:Dexterity+Stealth+WP difficulty:7`\n\n"
            "Where `SwordAttack` is a saved macro."
        ),
        inline=False
    )

    embed.add_field(
        name="Expressions",
        value=(
            "Expressions can include:\n"
            "- Attributes, Abilities, Disciplines, Backgrounds, etc.\n"
            "- Numbers (e.g., `+3`, `-1`)\n"
            "- [Specializations] (e.g., `Melee[Swords]`)\n"
            "- `+` or `-` between tokens\n"
            "- `willpower` refers to **Current Willpower**\n"
            "- `willmax` refers to **Maximum Willpower**\n\n"
            "**Example:** `Dexterity+Melee[Swords]+2`"
        ),
        inline=False
    )
    
    embed.add_field(
        name="Macros",
        value=(
            "If `roll_str` matches the name of a saved macro for the character, "
            "that macro's expression is resolved automatically."
        ),
        inline=False
    )

    embed.add_field(
        name="Willpower",
        value=(
            "Include `+WP` at the end of your expression or macro name to spend Willpower "
            "for an automatic success.\n\n"
            "**Example:** `Dexterity+Stealth+WP`"
        ),
        inline=False
    )

    embed.add_field(
        name="Difficulty",
        value=(
            "The `difficulty` parameter determines how high each die must roll to count as a success.\n"
            "Typical values are 6 or 7."
        ),
        inline=False
    )

    embed.add_field(
        name="Comments",
        value=(
            "Use the optional `comment` field to include a short message with your roll.\n\n"
            "**Example:** `/roll name:Aldric roll_str:Dexterity+Melee difficulty:6 comment:\"Attack #1\"`"
        ),
        inline=False
    )

    embed.add_field(
        name="Botches and Specializations",
        value=(
            "- A roll with more 1's than successes is a **botch**.\n"
            "- If a specialization applies, 10's count as double successes."
        ),
        inline=False
    )

    return embed


# ---------------------------
# DTA HELP EMBED FUNCTION
# ---------------------------
def get_dta_help_embed() -> discord.Embed:
    """Return an embed explaining the DTA system and its commands."""
    embed = discord.Embed(
        title="DTA Help",
        description=(
            "DTA (Downtime Actions) represents time or effort that a character has accrued "
            "and can spend between sessions on actions like research, crafting, or influence.\n\n"
            "Use the commands below to log, spend, and sync DTA for your characters."
        ),
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="What is DTA?",
        value=(
            "- **Current DTA:** How many DTA points the character currently has.\n"
            "- **Total DTA:** How many DTA points the character has earned overall.\n"
            "- **DTA Log:** A running history of all DTA changes, including spending."
        ),
        inline=False
    )

    embed.add_field(
        name="Commands",
        value=(
            "`/dta log` – View the DTA log for a character.\n"
            "`/dta spend` – Spend DTA for a given reason (e.g., crafting, research).\n"
            "`/dta sync` – Sync the current DTA log to the character's sheet."
        ),
        inline=False
    )

    embed.add_field(
        name="/dta log",
        value=(
            "Displays the character's DTA history as a table, including date, delta (±DTA), result, and reason.\n"
            "Entries are listed from oldest to newest."
        ),
        inline=False
    )

    embed.add_field(
        name="/dta spend",
        value=(
            "Spends DTA from the character's current pool and records a log entry.\n\n"
            "**Example:** `/dta spend name:Aldric amount:3 reason:\"Research Project\"`"
        ),
        inline=False
    )

    embed.add_field(
        name="/dta sync",
        value=(
            "Uploads the character's current DTA values and log to their sheet.\n"
            "Use this after spending or gaining DTA to keep records up to date."
        ),
        inline=False
    )

    embed.set_footer(text="DTA = Downtime Actions")
    return embed

def get_character_help_embed() -> discord.Embed:
    """Returns a help embed explaining character commands."""
    embed = discord.Embed(
        title="Character Commands Help",
        description="Manage your characters, keywords, blood, and sheets.",
        color=discord.Color.dark_red()
    )

    # Initialization & Resync
    embed.add_field(
        name="`/character init <url>`",
        value=(
            "Adds a character to the database by connecting a Google Sheet.\n"
            "Make sure the Sheet is set to 'Anyone with the link can edit'."
        ),
        inline=False
    )

    embed.add_field(
        name="`/character resync <name>`",
        value="Force refreshes the character from their Google Sheet, updating stats and nickname.",
        inline=False
    )

    # Viewing
    embed.add_field(
        name="`/character show <name>`",
        value=(
            "Displays a paginated view of a character's sheet information.\n"
            "- Page 1: Attributes & Abilities\n"
            "- Page 2: Disciplines, Backgrounds, Merits, Flaws, Virtues\n"
            "- Page 3: Rituals & Sorcery Paths (if applicable)"
        ),
        inline=False
    )

    # Keyword
    embed.add_field(
        name="`/character keyword <name> <new_keyword>`",
        value="Changes the keyword used for shorthand rolls or Tupper linking.",
        inline=False
    )

    # Blood
    embed.add_field(
        name="`/character adjust-blood <name> <amount> <comment>`",
        value=(
            "Adjusts a character’s blood pool by a positive or negative amount.\n"
            "Automatically logs the change and can trigger Hunger Torpor if the pool hits 0."
        ),
        inline=False
    )

    embed.add_field(
        name="`/character blood-log <uuid>`",
        value="Displays a character’s full blood log in a formatted table.",
        inline=False
    )

    # Hunting
    embed.add_field(
        name="`/character hunt <name> <hunt_str> <difficulty> [comment]`",
        value=(
            "Rolls for hunting using the specified roll string.\n"
            "• Supports WP expenditure.\n"
            "• Auto-applies Efficient Digestion if present.\n"
            "• Updates blood pool on success."
        ),
        inline=False
    )

    embed.set_footer(text="Use autocomplete for character names where available.")
    return embed

def get_st_help_embed() -> discord.Embed:
    """Returns a help embed explaining Storyteller (ST) commands."""
    embed = discord.Embed(
        title="ST Commands Help",
        description=(
            "These commands are **restricted to users with ST roles** as defined in your `.env` file.\n"
            "They allow Storytellers to perform weekly maintenance, distribute Downtime Actions (DTA), "
            "and keep player Google Sheets synchronized with reference templates."
        ),
        color=discord.Color.gold()
    )

    # Role Requirement
    embed.add_field(
        name="Role Requirement",
        value=(
            "All ST commands require the user to have at least one of the roles listed in the `.env` variable `ROLES`.\n"
            "If a user without the correct role attempts to run these commands, they will receive an error message."
        ),
        inline=False
    )

    # /reset
    embed.add_field(
        name="`/reset`",
        value=(
            "Performs the **weekly reset** for all characters:\n"
            "• Grants each character their configured weekly DTA (from `.env` `WEEKLY_DTA`).\n"
            "• Resets all characters' **Willpower** to their maximum.\n"
            "• Logs the DTA gain to each character's sheet.\n"
            "• Sends a summary announcement listing all affected characters."
        ),
        inline=False
    )

    # /update-sheets
    embed.add_field(
        name="`/update-sheets`",
        value=(
            "Synchronizes **reference tabs** from the base Google Sheet (defined in `.env` as `BASE_SHEET`) "
            "to every character's sheet.\n"
            "Tabs in `EXCLUDED_TABS` are skipped (e.g., Character Sheet, Inventory, Logs).\n"
            "Existing content in matching tabs is cleared and replaced with the base sheet's content.\n\n"
            "This is useful when you update a system reference table, rules, or downtime actions "
            "and want those changes to appear in all player sheets."
        ),
        inline=False
    )

    # Excluded Tabs info
    embed.add_field(
        name="Excluded Tabs",
        value=(
            "The following tabs are skipped during sheet updates:\n"
            "```text\n"
            "!START HERE!, Character Sheet, Combat & Contacts, Backstory & Backgrounds,\n"
            "Inventory & Notes, XP & Downtime Logs, Your Retainers,\n"
            "Your Haven / Domain, Your Blood Storage\n"
            "```"
        ),
        inline=False
    )

    embed.set_footer(text="ST = Storyteller. These commands are restricted to designated roles.")
    return embed

def requires_st_role():
    """Custom check to ensure the user has one of the allowed ST roles."""
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            raw_roles = config.get("ROLES", "[]")
            try:
                allowed_roles = ast.literal_eval(raw_roles)
            except Exception:
                allowed_roles = [r.strip() for r in raw_roles.split(",")]

            user_roles = [r.name for r in getattr(interaction.user, "roles", [])]
            if any(r in user_roles for r in allowed_roles):
                return True

            # Deny access with message
            await interaction.response.send_message(
                "You do not have the correct role to use this command.",
                ephemeral=True
            )
            return False
        except Exception as e:
            return

    return app_commands.check(predicate)