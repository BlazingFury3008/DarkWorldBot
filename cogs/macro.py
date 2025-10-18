import discord
from discord.ext import commands
from discord import app_commands

from libs.character import Character
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
    # Macro Command Group
    # ---------------------------
    macro = app_commands.Group(
        name="macro",
        description="Commands related to character macros"
    )

    # ---------------------------
    # CREATE MACRO
    # ---------------------------
    @macro.command(name="new", description="Create a new macro for your character.")
    @app_commands.describe(
        name="Name of the new macro.",
        macro_str="The dice expression (e.g., Dexterity+Melee+2)."
    )
    async def create_macro(
        self,
        interaction: discord.Interaction,
        name: str,
        macro_str: str
    ):
        user_id = str(interaction.user.id)
        try:
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.response.send_message(
                    "You don't have a character registered yet. Use `/character init` first.",
                    ephemeral=True
                )
                return

            if not name.strip() or not macro_str.strip():
                await interaction.response.send_message(
                    "Macro name and expression cannot be empty.",
                    ephemeral=True
                )
                return

            if "+WP" in macro_str.upper():
                await interaction.response.send_message(
                    "Macros cannot contain '+WP'. Willpower must be added manually when rolling.",
                    ephemeral=True
                )
                return

            valid, error = validate_macro(f"{name}={macro_str}")
            if not valid:
                await interaction.response.send_message(f"Invalid macro format: {error}", ephemeral=True)
                return

            total_pool, _, specs_applied = resolve_dice_pool(macro_str, char)
            if total_pool == -1:
                await interaction.response.send_message(
                    "Macro expression could not be resolved. Check for missing traits or invalid specializations.",
                    ephemeral=True
                )
                return

            # Ensure macros attribute exists
            if not isinstance(getattr(char, "macros", None), dict):
                char.macros = {}

            if name in char.macros:
                await interaction.response.send_message(
                    f"A macro named '{name}' already exists. Use `/macro update` to modify it.",
                    ephemeral=True
                )
                return

            char.macros[name] = macro_str
            char.save_parsed()

            specs_text = f" (using {', '.join(specs_applied)})" if specs_applied else ""
            await interaction.response.send_message(
                f"Macro '{name}' created successfully.\nDicepool: {total_pool}{specs_text}",
                ephemeral=True
            )

            logger.info(f"User {user_id} created macro '{name}' for {char.name} ({total_pool} dice).")

        except Exception as e:
            logger.exception(f"Error creating macro for user {user_id}: {e}")
            await interaction.response.send_message(f"Error creating macro: {e}", ephemeral=True)

    # ---------------------------
    # UPDATE MACRO
    # ---------------------------
    @macro.command(name="update", description="Update an existing macro for your character.")
    @app_commands.describe(
        name="Name of the macro to update.",
        macro_str="New dice expression."
    )
    async def update_macro(
        self,
        interaction: discord.Interaction,
        name: str,
        macro_str: str
    ):
        user_id = str(interaction.user.id)
        try:
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.response.send_message(
                    "You don't have a character registered yet. Use `/character init` first.",
                    ephemeral=True
                )
                return

            if "+WP" in macro_str.upper():
                await interaction.response.send_message(
                    "Macros cannot contain '+WP'. Willpower must be added manually when rolling.",
                    ephemeral=True
                )
                return

            valid, error = validate_macro(f"{name}={macro_str}")
            if not valid:
                await interaction.response.send_message(f"Invalid macro format: {error}", ephemeral=True)
                return

            total_pool, _, specs_applied = resolve_dice_pool(macro_str, char)
            if total_pool == -1:
                await interaction.response.send_message(
                    "Macro expression could not be resolved. Check for missing traits or invalid specializations.",
                    ephemeral=True
                )
                return

            if not isinstance(getattr(char, "macros", None), dict) or name not in char.macros:
                await interaction.response.send_message(
                    f"No existing macro named '{name}' found.",
                    ephemeral=True
                )
                return

            char.macros[name] = macro_str
            char.save_parsed()

            specs_text = f" (using {', '.join(specs_applied)})" if specs_applied else ""
            await interaction.response.send_message(
                f"Macro '{name}' updated successfully.\nDicepool: {total_pool}{specs_text}",
                ephemeral=True
            )

            logger.info(f"User {user_id} updated macro '{name}' for {char.name} ({total_pool} dice).")

        except Exception as e:
            logger.exception(f"Error updating macro for user {user_id}: {e}")
            await interaction.response.send_message(f"Error updating macro: {e}", ephemeral=True)

    # ---------------------------
    # LIST MACROS
    # ---------------------------
    @macro.command(name="list", description="List all macros for your character.")
    async def list_macros(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        try:
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.response.send_message(
                    "You don't have a character registered yet. Use `/character init` first.",
                    ephemeral=True
                )
                return

            macros = getattr(char, "macros", {}) or {}
            if not macros:
                await interaction.response.send_message(
                    "You have no saved macros.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"Macros for {char.name}",
                color=discord.Color.blurple()
            )

            for macro_name, macro_expr in macros.items():
                total, _, specs_applied = resolve_dice_pool(macro_expr, char)
                value_str = (
                    "Invalid or unknown traits"
                    if total == -1
                    else f"Dicepool: {total}" + (f" (using {', '.join(specs_applied)})" if specs_applied else "")
                )

                embed.add_field(
                    name=macro_name,
                    value=f"{macro_expr}\n{value_str}",
                    inline=False
                )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"Error listing macros for user {user_id}: {e}")
            await interaction.response.send_message(f"Error listing macros: {e}", ephemeral=True)

    # ---------------------------
    # DELETE MACRO
    # ---------------------------
    @macro.command(name="delete", description="Delete a macro from your character.")
    @app_commands.describe(name="Name of the macro to delete.")
    async def delete_macro(self, interaction: discord.Interaction, name: str):
        user_id = str(interaction.user.id)
        try:
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.response.send_message(
                    "You don't have a character registered yet. Use `/character init` first.",
                    ephemeral=True
                )
                return

            if not isinstance(getattr(char, "macros", None), dict) or name not in char.macros:
                await interaction.response.send_message(f"No macro named '{name}' found.", ephemeral=True)
                return

            del char.macros[name]
            char.save_parsed()

            await interaction.response.send_message(f"Macro '{name}' deleted.", ephemeral=True)
            logger.info(f"User {user_id} deleted macro '{name}' for {char.name}.")

        except Exception as e:
            logger.exception(f"Error deleting macro for user {user_id}: {e}")
            await interaction.response.send_message(f"Error deleting macro: {e}", ephemeral=True)


# ---------------------------
# Cog Setup Function
# ---------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Macro(bot))
