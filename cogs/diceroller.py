from discord.ext import commands
from discord import app_commands
import discord
from libs.database_loader import *
from libs.character import *
from libs.macro import *
from libs.roller import process_willpower, resolve_dice_pool, roll_dice, build_roll_embed, handle_botch_mention
from dotenv import dotenv_values
from libs.help import get_roll_help_embed

config = dotenv_values(".env")

from typing import List
import re
import logging
logger = logging.getLogger(__name__)

class Diceroller(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Registered Diceroller")

    # ---------------------------
    # Autocomplete Helper
    # ---------------------------
    async def _character_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> List[app_commands.Choice[str]]:
        user_id = str(interaction.user.id)
        try:
            names = list_characters_for_user(user_id) or []
        except Exception as e:
            logger.error(f"Autocomplete error: {e}")
            names = []

        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()
        ][:25]

    # ---------------------------
    # Helper: Expand macros anywhere in expression
    # ---------------------------
    def _expand_macro_expression(self, char: Character, roll_str: str) -> str:
        """
        Expand any macro names found anywhere in the expression, without adding parentheses
        (your resolver doesn't support them). Works for:
        Sword+5, 5+Sword, Dexterity+Sword+2, Sword+Rituals+WP, etc.
        """
        macros = getattr(char, "macros", {}) or {}
        if not macros:
            return roll_str

        # Case-insensitive lookup (optional but user-friendly)
        macro_lookup = {k.lower(): v for k, v in macros.items()}

        # Split on + and - while keeping the operators
        tokens = re.split(r'([+-])', roll_str)
        expanded_tokens = []

        for token in tokens:
            t = token.strip()

            # Preserve operators exactly
            if t in {"+", "-"}:
                expanded_tokens.append(t)
                continue

            # Replace token if it's a macro name
            if t.lower() in macro_lookup:
                expanded_tokens.append(macro_lookup[t.lower()])
            else:
                # Keep the original token (trimmed)
                expanded_tokens.append(t)

        expanded = "".join(expanded_tokens)
        logger.debug(f"[MACRO EXPAND] {roll_str} -> {expanded}")
        return expanded
    
    # ---------------------------
    # /roll Command
    # ---------------------------
    @app_commands.command(name="roll", description="Roll dice using a macro or expression")
    @app_commands.describe(
        name="Character name",
        roll_str="Macro name or expression (e.g. Dexterity+Melee or Attack+4+WP)",
        difficulty="Difficulty of the roll",
        comment="Optional comment to display with the roll"
    )
    async def roll(
        self,
        interaction: discord.Interaction,
        name: str,
        roll_str: str,
        difficulty: int,
        comment: str = None
    ):
        await interaction.response.defer()

        try:
            # Load character
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)
            if not char:
                await interaction.followup.send(f"No character named {name} found.")
                return

            # Expand macros anywhere in the expression
            expanded_str = self._expand_macro_expression(char, roll_str)
            logger.debug(f"[ROLL] Expanded expression: {roll_str} → {expanded_str}")

            # Handle Willpower
            expanded_str, willpower_used = process_willpower(expanded_str, char)

            # Dice pool
            total_pool, spec_used, specs_applied = resolve_dice_pool(expanded_str, char)
            if total_pool == -1:
                await interaction.followup.send(
                    "Unable to roll this pool. Check your syntax and try again.",
                )
                return

            # Dice roll
            formatted, successes, botch, ones_count = roll_dice(
                total_pool, spec_used, difficulty, return_ones=True
            )

            # Apply Willpower auto-success
            if willpower_used:
                if ones_count > 0:
                    ones_count -= 1
                    logger.debug("[ROLL] Willpower success canceled by a '1'")
                else:
                    successes += 1
                    formatted.append("*WP*")

            # Build Embed
            embed = build_roll_embed(
                interaction, total_pool, difficulty, successes, botch,
                formatted, specs_applied, expanded_str, comment, willpower_used
            )

            await interaction.followup.send(embed=embed)

            # Botch role ping
            if botch:
                await handle_botch_mention(interaction, char.name)

        except ValueError as ve:
            await interaction.followup.send(str(ve), ephemeral=True)
        except Exception as e:
            logger.exception(f"[ROLL] Roll command error: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @roll.autocomplete("name")
    async def roll_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)