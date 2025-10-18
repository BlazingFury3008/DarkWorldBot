import discord
from discord.ext import commands
from discord import app_commands
from dotenv import dotenv_values
import re
import logging

from libs.database_loader import *
from libs.character import Character
from libs.macro import *
from libs.roller import (
    process_willpower,
    resolve_dice_pool,
    roll_dice,
    build_roll_embed,
    handle_botch_mention
)
from libs.help import get_roll_help_embed

# Load configuration
config = dotenv_values(".env")

logger = logging.getLogger(__name__)


class Diceroller(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Registered Diceroller Cog")

    # ---------------------------
    # Helper: Expand macros anywhere in expression
    # ---------------------------
    def _expand_macro_expression(self, char: Character, roll_str: str) -> str:
        """
        Expand any macro names found anywhere in the expression,
        e.g. Sword+5, Dexterity+Sword+WP, etc.
        """
        macros = getattr(char, "macros", {}) or {}
        if not macros:
            return roll_str

        macro_lookup = {k.lower(): v for k, v in macros.items()}

        # Normalize whitespace and split by arithmetic symbols
        tokens = re.split(r'([+\-*/])', roll_str.replace(" ", ""))
        expanded_tokens = []

        for token in tokens:
            t = token.strip()
            if t in {"+", "-", "*", "/"}:
                expanded_tokens.append(t)
                continue
            if t.lower() in macro_lookup:
                expanded_tokens.append(macro_lookup[t.lower()])
            else:
                expanded_tokens.append(t)

        expanded = "".join(expanded_tokens)
        logger.debug(f"[MACRO EXPAND] {roll_str} → {expanded}")
        return expanded

    # ---------------------------
    # /roll Command
    # ---------------------------
    @app_commands.command(name="roll", description="Roll dice using a macro or expression.")
    @app_commands.describe(
        roll_str="Macro or dice expression (e.g. Dexterity+Melee or Attack+4+WP)",
        difficulty="Difficulty threshold for successes.",
        comment="Optional note to display with the roll."
    )
    async def roll(
        self,
        interaction: discord.Interaction,
        roll_str: str,
        difficulty: int,
        comment: str = None
    ):
        """Perform a dice roll for the user's current character."""
        # Private rolls by default
        await interaction.response.defer(ephemeral=True)

        user_id = str(interaction.user.id)

        try:
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.followup.send(
                    "You don't have a character registered yet. Use `/character init` first.",
                    ephemeral=True
                )
                return

            # Expand macros within the expression
            expanded_str = self._expand_macro_expression(char, roll_str)
            logger.debug(f"[ROLL] Expression: {roll_str} → {expanded_str}")

            # Handle Willpower
            expanded_str, willpower_used = process_willpower(expanded_str, char)
            logger.debug(f"[ROLL] Willpower used: {willpower_used}")

            # Resolve total dice pool
            total_pool, spec_used, specs_applied = resolve_dice_pool(expanded_str, char)
            if total_pool == -1:
                await interaction.followup.send(
                    "Unable to roll this pool. Check your syntax, attributes, or macro names.",
                    ephemeral=True
                )
                return

            # Roll dice
            try:
                formatted, successes, botch, ones_count = roll_dice(
                    total_pool, spec_used, difficulty, return_ones=True
                )
            except Exception as e:
                logger.error(f"[ROLL] Dice rolling failed: {e}")
                await interaction.followup.send("Dice roll failed to execute.", ephemeral=True)
                return

            # Apply Willpower auto-success
            if willpower_used:
                if ones_count > 0:
                    ones_count -= 1
                    logger.debug("[ROLL] Willpower success canceled by a rolled 1.")
                else:
                    successes += 1
                    formatted.append("*WP*")

            # Build the roll result embed
            embed = build_roll_embed(
                interaction=interaction,
                total_pool=total_pool,
                difficulty=difficulty,
                successes=successes,
                botch=botch,
                formatted=formatted,
                specs_applied=specs_applied,
                expression=expanded_str,
                comment=comment,
                willpower_used=willpower_used,
            )

            await interaction.followup.send(embed=embed, ephemeral=True)

            # Notify storyteller or channel on botch
            if botch:
                await handle_botch_mention(interaction, char.name)

            logger.info(
                f"[ROLL] User {interaction.user} rolled {total_pool} dice (Diff {difficulty}) "
                f"→ {successes} succ | Botch: {botch}"
            )

        except ValueError as ve:
            logger.warning(f"[ROLL] Invalid input from user {user_id}: {ve}")
            await interaction.followup.send(str(ve), ephemeral=True)
        except Exception as e:
            logger.exception(f"[ROLL] Unexpected error for user {user_id}: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


# ---------------------------
# Cog Setup Function
# ---------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Diceroller(bot))
