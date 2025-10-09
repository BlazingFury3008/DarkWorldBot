from discord.ext import commands
from discord import app_commands
import discord
from libs.database_loader import *
from libs.character import *
from libs.macro import *
from libs.roller import *
from dotenv import dotenv_values

import logging
import ast
from typing import List

config = dotenv_values(".env")

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
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete character names for the current user"""
        user_id = str(interaction.user.id)
        try:
            names = list_characters_for_user(user_id) or []
            # ensure they are strings
            names = [n for n in names if isinstance(n, str)]
            logger.debug(f"Autocomplete names for {user_id}: {names}")
        except Exception as e:
            logger.error(f"Autocomplete error: {e}")
            names = []

        current_lower = current.lower()
        return [
            app_commands.Choice(name=n, value=n)
            for n in names if current_lower in n.lower()
        ][:25]

    # ---------------------------
    # /roll Command (Top-Level)
    # ---------------------------
    @app_commands.command(name="roll", description="Roll dice using a macro or expression")
    @app_commands.describe(
        name="Character name",
        roll_str="Macro name or expression (e.g. Dexterity+Melee)",
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
            logger.info(f"[ROLL] User '{interaction.user}' rolling for character '{name}' with expr='{roll_str}' (Diff {difficulty})")

            total_pool = -1
            spec_used = False
            specs_applied = []

            # Load character
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)
            if not char:
                logger.warning(f"[ROLL] Character '{name}' not found for user {user_id}")
                await interaction.followup.send(
                    f"No character named {name} found.", ephemeral=True
                )
                return

            # --- Macro Check ---
            macro_str = get_character_macro(char.uuid)
            if macro_str:
                logger.debug(f"[ROLL] Found macros for {char.name}: {macro_str}")
                macros = macro_str.split(";")
                for macro in macros:
                    if "=" not in macro:
                        continue
                    name_part, expr = macro.split("=", 1)
                    if roll_str == name_part:
                        total_pool, spec_used, specs_applied = sum_macro(expr, char=char)
                        logger.debug(f"[ROLL] Using macro '{name_part}' → pool={total_pool}, specs={specs_applied}")
                        break

            # --- Expression Check ---
            if total_pool == -1:
                total_pool, spec_used, specs_applied = sum_macro(roll_str, char=char)
                logger.debug(f"[ROLL] Using expression '{roll_str}' → pool={total_pool}, specs={specs_applied}")

            if total_pool == -1:
                logger.error(f"[ROLL] Unable to resolve pool for '{roll_str}'")
                await interaction.followup.send(
                    "Unable to roll this pool. Check your syntax and try again.",
                    ephemeral=True,
                )
                return

            # --- Roll Dice ---
            formatted, successes, botch = roll_dice(total_pool, spec_used, difficulty)
            logger.info(
                f"[ROLL] Dice rolled → pool={total_pool}, successes={successes}, botch={botch}, formatted={formatted}"
            )

            embed = discord.Embed(
                title=f"{interaction.user.display_name or interaction.user.name}: Pool {total_pool}, Diff {difficulty}",
                color=(discord.Color.dark_red() if successes == 0 else discord.Color.green())
            )

            # Result summary
            embed.add_field(
                name=(f"{successes} Success{'es' if successes != 1 else ''}" if not botch else "BOTCH"),
                value=" ",
                inline=False
            )

            # Dice results
            embed.add_field(name="Dice", value=" ".join(formatted), inline=True)

            # Specialties used
            if specs_applied:
                embed.add_field(
                    name="Specialties Applied",
                    value=", ".join(specs_applied),
                    inline=True
                )
            else:
                embed.add_field(
                    name="Specialties Applied",
                    value="None",
                    inline=True
                )

            # Original roll string + optional comment
            footer_value = f"-# {roll_str}"
            if comment:
                footer_value += f"\n\n-# {comment}"

            embed.add_field(name="", value=footer_value, inline=False)

            # Delete ephemeral response
            try:
                await interaction.delete_original_response()
            except Exception as e:
                logger.debug(f"[ROLL] Could not delete original response: {e}")

            # Send public result
            await interaction.channel.send(embed=embed)

            # --- Botch Role Mention ---
            if botch:
                logger.info(f"[ROLL] Botch detected for {char.name}. Attempting role mention...")
                try:
                    roles_env = config.get("ROLES", "[]")
                    logger.debug(f"[ROLL] Raw ROLES env: {roles_env}")

                    try:
                        role_names = ast.literal_eval(roles_env)
                        logger.debug(f"[ROLL] Parsed role names (ast): {role_names}")
                    except Exception:
                        logger.warning("[ROLL] ROLES env variable invalid. Using empty list.")
                        role_names = []

                    if role_names:
                        guild_roles = interaction.guild.roles
                        logger.debug(f"[ROLL] Guild roles: {[r.name for r in guild_roles]}")

                        mentionable_roles = [
                            next((r for r in guild_roles if r.name.lower() == role_name.lower()), None)
                            for role_name in role_names
                        ]
                        mentionable_roles = [r for r in mentionable_roles if r is not None]

                        if mentionable_roles:
                            mentions = " ".join([r.mention for r in mentionable_roles])
                            await interaction.channel.send(f"BOTCH by {char.name} — {mentions}")
                            logger.info(f"[ROLL] Sent botch ping: {mentions}")
                        else:
                            logger.warning(f"[ROLL] No matching roles found for: {role_names}")
                    else:
                        logger.debug("[ROLL] No roles set for botch mention.")

                except Exception as botch_err:
                    logger.exception(f"[ROLL] Error during botch mention: {botch_err}")

        except Exception as e:
            logger.exception(f"[ROLL] Roll command error: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)


    @roll.autocomplete("name")
    async def roll_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)
