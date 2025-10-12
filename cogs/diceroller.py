from discord.ext import commands
from discord import app_commands
import discord
from libs.database_loader import *
from libs.character import *
from libs.macro import *
from libs.roller import process_willpower, resolve_dice_pool, roll_dice, build_roll_embed, handle_botch_mention
from dotenv import dotenv_values
config = dotenv_values(".env")

import logging
from typing import List, Tuple


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
    # /roll Command
    # ---------------------------
    @app_commands.command(name="roll", description="Roll dice using a macro or expression")
    @app_commands.describe(
        name="Character name",
        roll_str="Macro name or expression (e.g. Dexterity+Melee or Attack+WP)",
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
        await interaction.response.defer(ephemeral=True)

        try:
            # Load character
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)
            if not char:
                await interaction.followup.send(f"No character named {name} found.", ephemeral=True)
                return

            # Willpower
            roll_str, willpower_used = process_willpower(roll_str, char)

            # Dice pool
            total_pool, spec_used, specs_applied = resolve_dice_pool(roll_str, char)
            if total_pool == -1:
                await interaction.followup.send(
                    "Unable to roll this pool. Check your syntax and try again.",
                    ephemeral=True,
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
                formatted, specs_applied, roll_str, comment, willpower_used
            )

            # Replace ephemeral with public message
            try:
                await interaction.delete_original_response()
            except Exception:
                pass

            await interaction.channel.send(embed=embed)

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
