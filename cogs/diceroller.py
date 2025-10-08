from discord.ext import commands
from discord import app_commands, Role
import discord
from libs.database_loader import *
from libs.character import *
from libs.macro import *
from libs.roller import *

import logging

logger = logging.getLogger(__name__)

class Diceroller(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered Diceroller")
        
    # ---------------------------
    # Autocomplete Helper
    # ---------------------------
    async def _character_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete character names for the current user"""
        user_id = str(interaction.user.id)
        try:
            names = list_characters_for_user(user_id) or []
            logger.debug(f"Autocomplete names for {user_id}: {names}")
        except Exception as e:
            logger.error(f"Autocomplete error: {e}")
            names = []
        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current.lower() in n.lower()
        ][:25]

    # ---------------------------
    # /roll Command (Top-Level)
    # ---------------------------
    @app_commands.command(name="roll", description="Roll dice using a macro or expression")
    async def roll(self, interaction: discord.Interaction, name: str, roll_str: str, difficulty: int):
        # Always defer ephemerally so errors stay private
        await interaction.response.defer(ephemeral=True)
        try:
            total_pool = -1
            spec = False
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)
            if not char:
                await interaction.followup.send(
                    f"No character named `{name}` found.", ephemeral=True
                )
                return

            # --- Macro Check ---
            macro_str = get_character_macro(char.uuid)
            if macro_str:
                macros = macro_str.split(";")
                for macro in macros:
                    if "=" not in macro:
                        continue
                    name_part, expr = macro.split("=", 1)
                    if roll_str == name_part:
                        total_pool, spec = sum_macro(expr, char=char)
                        break

            # --- Expression Check ---
            if total_pool == -1:
                total_pool, spec = sum_macro(roll_str, char=char)

            if total_pool == -1:
                await interaction.followup.send(
                    "Unable to roll this pool. Check your syntax and try again.",
                    ephemeral=True,
                )
                return

            # --- Roll Dice ---
            formatted, successes, botch = roll_dice(total_pool, spec, difficulty)
            embed = discord.Embed(
                title=f"{interaction.user.display_name or interaction.user.name}: Pool {total_pool}, Diff {difficulty}",
                color=(discord.Color.dark_red() if successes == 0 else discord.Color.green())
            )
            embed.add_field(
                name=(f"{successes} Success{'es' if successes != 1 else ''}" if not botch else "💥 **BOTCH!**"),
                value=" ",
                inline=False
            )
            embed.add_field(name="Dice", value=" ".join(formatted), inline=True)
            embed.add_field(name="Specialty", value=str(spec), inline=True)
            embed.add_field(name="", value=f"-# {roll_str}", inline=False)

            # Delete the ephemeral defer response
            try:
                await interaction.delete_original_response()
            except Exception:
                pass

            # Send a public message with the roll result
            await interaction.channel.send(embed=embed)

        except Exception as e:
            print(e)
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @roll.autocomplete("name")
    async def roll_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)
