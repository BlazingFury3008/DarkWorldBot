from discord.ext import commands
from discord import app_commands
import discord

from libs.character import Character, list_characters_for_user
from libs.macro import validate_macro
from libs.roller import resolve_dice_pool
from libs.help import get_macro_help_embed 

import logging
logger = logging.getLogger(__name__)


class Macro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Registered Macro Cog")

    # ---------------------------
    # Character Autocomplete Helper
    # ---------------------------
    async def _character_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete character names for the current user"""
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
    # Macro Command Group
    # ---------------------------
    macro = app_commands.Group(
        name="macro", description="All commands related to macros"
    )

    # ---------------------------
    # CREATE MACRO
    # ---------------------------
    @macro.command(name="new", description="Create a new macro for a character")
    async def create_macro(
        self,
        interaction: discord.Interaction,
        character: str,
        name: str,
        macro_str: str
    ):
        user_id = interaction.user.id
        try:
            char = Character.load_by_name(name=character, user_id=user_id)

            # Step 0: Prevent +WP usage
            if "+WP" in macro_str.upper():
                await interaction.response.send_message(
                    "Macros cannot contain '+WP'. Willpower must be added at roll time.",
                    ephemeral=True
                )
                return

            # Step 1: Validate syntax
            valid, error = validate_macro(f"{name}={macro_str}")
            if not valid:
                await interaction.response.send_message(f"Invalid macro format: {error}", ephemeral=True)
                return

            # Step 2: Ensure expression can be resolved
            total_pool, spec_used, specs_applied = resolve_dice_pool(macro_str, char)
            if total_pool == -1:
                await interaction.response.send_message(
                    f"Macro expression could not be resolved for {character}. Check for missing traits or invalid specializations.",
                    ephemeral=True
                )
                return

            # Step 3: Save
            if not hasattr(char, "macros") or char.macros is None:
                char.macros = {}

            if name in char.macros:
                await interaction.response.send_message(
                    f"A macro named '{name}' already exists. Use /macro update to modify it.",
                    ephemeral=True
                )
                return

            char.macros[name] = macro_str
            char.save_parsed()

            value_str = f"Dicepool: {total_pool}"
            if specs_applied:
                value_str += f" (using {', '.join(specs_applied)})"

            await interaction.response.send_message(
                f"Macro '{name}' created for {character}.\n{value_str}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error creating macro: {e}")
            await interaction.response.send_message(f"Error creating macro: {e}", ephemeral=True)

    @create_macro.autocomplete("character")
    async def create_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)

    # ---------------------------
    # UPDATE MACRO
    # ---------------------------
    @macro.command(name="update", description="Update an existing macro for a character")
    async def update_macro(
        self,
        interaction: discord.Interaction,
        character: str,
        name: str,
        macro_str: str
    ):
        user_id = interaction.user.id
        try:
            char = Character.load_by_name(name=character, user_id=user_id)

            # Step 0: Prevent +WP usage
            if "+WP" in macro_str.upper():
                await interaction.response.send_message(
                    "Macros cannot contain '+WP'. Willpower must be added at roll time.",
                    ephemeral=True
                )
                return

            # Step 1: Validate syntax
            valid, error = validate_macro(f"{name}={macro_str}")
            if not valid:
                await interaction.response.send_message(f"Invalid macro format: {error}", ephemeral=True)
                return

            # Step 2: Ensure expression can be resolved
            total_pool, spec_used, specs_applied = resolve_dice_pool(macro_str, char)
            if total_pool == -1:
                await interaction.response.send_message(
                    f"Macro expression could not be resolved for {character}. Check for missing traits or invalid specializations.",
                    ephemeral=True
                )
                return

            if not hasattr(char, "macros") or name not in char.macros:
                await interaction.response.send_message(
                    f"No existing macro named '{name}' found.",
                    ephemeral=True
                )
                return

            char.macros[name] = macro_str
            char.save_parsed()

            value_str = f"Dicepool: {total_pool}"
            if specs_applied:
                value_str += f" (using {', '.join(specs_applied)})"

            await interaction.response.send_message(
                f"Macro '{name}' updated for {character}.\n{value_str}",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Error updating macro: {e}")
            await interaction.response.send_message(f"Error updating macro: {e}", ephemeral=True)

    @update_macro.autocomplete("character")
    async def update_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)

    # ---------------------------
    # LIST MACROS
    # ---------------------------
    @macro.command(name="list", description="List all macros for a character with dicepool values")
    async def list_macros(self, interaction: discord.Interaction, character: str):
        user_id = interaction.user.id
        try:
            char = Character.load_by_name(name=character, user_id=user_id)
            macros = getattr(char, "macros", {}) or {}

            if not macros:
                await interaction.response.send_message(f"{character} has no saved macros.", ephemeral=True)
                return

            embed = discord.Embed(
                title=f"Macros for {character}",
                color=discord.Color.blurple()
            )

            for macro_name, macro_expr in macros.items():
                total, used_spec, specs_applied = resolve_dice_pool(macro_expr, char)
                if total == -1:
                    value_str = "Invalid or unknown traits"
                else:
                    value_str = f"Dicepool: {total}"
                    if specs_applied:
                        value_str += f" (using {', '.join(specs_applied)})"

                embed.add_field(
                    name=macro_name,
                    value=f"{macro_expr}\n{value_str}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error listing macros: {e}")
            await interaction.response.send_message(f"Error listing macros: {e}", ephemeral=True)

    @list_macros.autocomplete("character")
    async def list_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)

    # ---------------------------
    # DELETE MACRO
    # ---------------------------
    @macro.command(name="delete", description="Delete a macro from a character")
    async def delete_macro(self, interaction: discord.Interaction, character: str, name: str):
        user_id = interaction.user.id
        try:
            char = Character.load_by_name(name=character, user_id=user_id)
            if not hasattr(char, "macros") or name not in char.macros:
                await interaction.response.send_message(f"No macro named '{name}' found.", ephemeral=True)
                return

            del char.macros[name]
            char.save_parsed()

            await interaction.response.send_message(f"Macro '{name}' deleted from {character}.", ephemeral=True)

        except Exception as e:
            logger.error(f"Error deleting macro: {e}")
            await interaction.response.send_message(f"Error deleting macro: {e}", ephemeral=True)

    @delete_macro.autocomplete("character")
    async def delete_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)