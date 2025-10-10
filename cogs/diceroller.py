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
from typing import List, Tuple

config = dotenv_values(".env")
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
    # Utility: Handle Willpower Token
    # ---------------------------
    def _process_willpower(self, roll_str: str, char: Character) -> Tuple[str, bool]:
        """Remove +WP from roll_str and spend Willpower if available"""
        if "+WP" not in roll_str.upper():
            return roll_str, False

        if char.curr_willpower < 1:
            raise ValueError(f"{char.name} does not have enough Willpower to spend!")

        cleaned = (
            roll_str.replace("+WP", "")
                    .replace("+wp", "")
                    .replace("+Wp", "")
                    .replace("+wP", "")
                    .strip()
        )
        char.curr_willpower -= 1
        char.save_parsed()
        logger.debug(f"[ROLL] Willpower spent for {char.name}. Remaining: {char.curr_willpower}")
        return cleaned, True

    # ---------------------------
    # Utility: Resolve Dice Pool
    # ---------------------------
    def _resolve_dice_pool(self, roll_str: str, char: Character) -> Tuple[int, bool, List[str]]:
        """Determine dice pool from either macro or expression"""
        macro_str = get_character_macro(char.uuid)
        if macro_str:
            for macro in macro_str.split(";"):
                if "=" not in macro:
                    continue
                name_part, expr = macro.split("=", 1)
                if roll_str.strip() == name_part.strip():
                    return sum_macro(expr, char=char)

        return sum_macro(roll_str, char=char)

    # ---------------------------
    # Utility: Format String
    # ---------------------------
    def format_roll_expression(self, expr: str) -> str:
        """
        Convert a raw roll expression into a more human-readable string.
        Example:
            Dexterity+Melee[Swords]+4   → "Rolling Dexterity, Melee (Swords) + 4 dice"
            Strength-2                 → "Rolling Strength - 2 dice"
        """
        if not expr or not isinstance(expr, str):
            return "Rolling (invalid expression)"

        # Split tokens by + or - but keep the sign
        tokens = re.findall(r"[+-]?\s*[^+-]+", expr)
        trait_parts = []
        dice_mods = []

        for token in tokens:
            token = token.strip()
            if not token:
                continue

            # Extract sign
            sign = "+"
            if token[0] in "+-":
                sign = token[0]
                token = token[1:].strip()

            # Numbers → dice modifiers
            if re.fullmatch(r"\d+", token):
                mod = f"{sign} {token} dice"
                dice_mods.append(mod)
                continue

            # Traits with optional spec
            m = re.match(r"([A-Za-z\s]+)(?:\[([^\]]+)\])?", token)
            if m:
                name = m.group(1).strip()
                spec = m.group(2)
                if spec:
                    trait_parts.append(f"{name} ({spec})")
                else:
                    trait_parts.append(name)
                continue

        # Join traits with commas, then add dice mods after
        trait_str = ", ".join(trait_parts) if trait_parts else ""
        mods_str = " ".join(dice_mods)

        if trait_str and mods_str:
            return f"Rolling {trait_str} {mods_str}"
        elif trait_str:
            return f"Rolling {trait_str}"
        elif mods_str:
            return f"Rolling {mods_str}"
        else:
            return "Rolling (empty expression)"

    # ---------------------------
    # Utility: Build Result Embed
    # ---------------------------
    def _build_roll_embed(
        self,
        interaction: discord.Interaction,
        total_pool: int,
        difficulty: int,
        successes: int,
        botch: bool,
        formatted: List[str],
        specs_applied: List[str],
        original_str: str,
        comment: str,
        willpower_used: bool
    ) -> discord.Embed:
        """Create the nicely formatted roll result embed"""
        color = discord.Color.dark_red() if successes == 0 else discord.Color.green()
        embed = discord.Embed(
            title=f"{interaction.user.display_name or interaction.user.name}: Pool {total_pool}, Diff {difficulty}",
            color=color
        )

        result_title = f"{successes} Success{'es' if successes != 1 else ''}" if not botch else "BOTCH"
        embed.add_field(name=result_title, value=" ", inline=False)

        embed.add_field(name="Dice", value=" ".join(formatted), inline=True)
        embed.add_field(
            name="Specialties Applied",
            value=", ".join(specs_applied) if specs_applied else "None",
            inline=True
        )

        footer_string = self.format_roll_expression(original_str)


        footer_value = f"-# {footer_string.strip()}"
        if willpower_used:
            footer_value += "; Willpower Used"
        if comment:
            footer_value += f"\n\n-# {comment}"
        embed.add_field(name="", value=footer_value, inline=False)

        return embed




    # ---------------------------
    # Utility: Botch Role Mention
    # ---------------------------
    async def _handle_botch_mention(self, interaction: discord.Interaction, char_name: str):
        """Mention storyteller roles on botch if configured"""
        try:
            roles_env = config.get("ROLES", "[]")
            try:
                role_names = ast.literal_eval(roles_env)
            except Exception:
                logger.warning("[ROLL] ROLES env variable invalid. Using empty list.")
                role_names = []

            if not role_names:
                return

            guild_roles = interaction.guild.roles
            mentionable_roles = [
                next((r for r in guild_roles if r.name.lower() == role_name.lower()), None)
                for role_name in role_names
            ]
            mentionable_roles = [r for r in mentionable_roles if r is not None]

            if mentionable_roles:
                mentions = " ".join([r.mention for r in mentionable_roles])
                await interaction.channel.send(f"BOTCH by {char_name} — {mentions}")
        except Exception as e:
            logger.exception(f"[ROLL] Error during botch mention: {e}")

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
            roll_str, willpower_used = self._process_willpower(roll_str, char)

            # Dice pool
            total_pool, spec_used, specs_applied = self._resolve_dice_pool(roll_str, char)
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
            embed = self._build_roll_embed(
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
                await self._handle_botch_mention(interaction, char.name)

        except ValueError as ve:
            await interaction.followup.send(str(ve), ephemeral=True)
        except Exception as e:
            logger.exception(f"[ROLL] Roll command error: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    @roll.autocomplete("name")
    async def roll_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)
