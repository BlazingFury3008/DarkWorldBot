import ast
import asyncio
import logging
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import dotenv_values

from libs.character import *
from libs.help import requires_st_role
from libs.database_loader import get_all_characters

config = dotenv_values(".env")

logger = logging.getLogger(__name__)

EXCLUDED_TABS = [
    "!START HERE!",
    "Character Sheet",
    "Combat & Contacts",
    "Backstory & Backgrounds",
    "Inventory & Notes",
    "XP & Downtime Logs",
    "Your Retainers",
    "Your Haven / Domain",
    "Your Blood Storage",
]


class ST(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Registered ST Commands")

    # ---------------------------
    # Slash Command: Reload Cogs (ST Only)
    # ---------------------------
    @app_commands.command(name="reload", description="Reload bot cogs (ST only).")
    @app_commands.describe(cog="Name of the cog to reload. Leave empty to reload all.")
    @requires_st_role()
    async def reload_cogs(self, interaction: discord.Interaction, cog: str = None):
        """Reload a specific cog or all cogs (requires ST role)."""
        await interaction.response.defer(ephemeral=True)

        logger.info(f"[RELOAD] Command triggered by {interaction.user} ({interaction.user.id})")

        try:
            # ---------------------------
            # Determine target cogs
            # ---------------------------
            if cog:
                cog_name = f"cogs.{cog}" if not cog.startswith("cogs.") else cog
                if cog_name in self.bot.extensions:
                    cogs_to_reload = [cog_name]
                    logger.info(f"[RELOAD] Target cog specified: {cog_name}")
                else:
                    logger.warning(f"[RELOAD] Cog not found: {cog_name}")
                    await interaction.followup.send(
                        f"Cog `{cog_name}` not found or not loaded.",
                        ephemeral=True
                    )
                    return
            else:
                cogs_to_reload = list(self.bot.extensions.keys())
                logger.info(f"[RELOAD] No cog specified. Reloading all ({len(cogs_to_reload)}) cogs.")

            # ---------------------------
            # Attempt reloads
            # ---------------------------
            reloaded = []
            failed = []

            for cog_name in cogs_to_reload:
                try:
                    logger.debug(f"[RELOAD] Attempting to reload: {cog_name}")
                    await self.bot.reload_extension(cog_name)
                    reloaded.append(cog_name)
                    logger.info(f"[RELOAD] Successfully reloaded {cog_name}")
                except Exception as e:
                    failed.append((cog_name, str(e)))
                    logger.exception(f"[RELOAD] Failed to reload {cog_name}: {e}")

            # ---------------------------
            # Build user response
            # ---------------------------
            lines = []

            if reloaded:
                lines.append("**Reloaded cogs:**")
                for r in reloaded:
                    lines.append(f"- `{r}`")
                logger.info(f"[RELOAD] Total successfully reloaded: {len(reloaded)}")

            if failed:
                lines.append("")
                lines.append("**Failed to reload:**")
                for f_name, f_error in failed:
                    lines.append(f"- `{f_name}` → {f_error}")
                logger.warning(f"[RELOAD] {len(failed)} cog(s) failed to reload.")

            if not reloaded and not failed:
                lines.append("No cogs were reloaded.")
                logger.warning("[RELOAD] No cogs to reload.")

            message = "\n".join(lines)
            await interaction.followup.send(message, ephemeral=True)

            # ---------------------------
            # Summary Log
            # ---------------------------
            logger.info(
                f"[RELOAD SUMMARY] {interaction.user} reloaded {len(reloaded)} cog(s); "
                f"{len(failed)} failed."
            )

        except Exception as e:
            logger.exception(f"[RELOAD] Unexpected error: {e}")
            await interaction.followup.send(
                f"An unexpected error occurred while reloading: {e}",
                ephemeral=True
            )

    # ---------------------------
    # Weekly Reset (ST Only)
    # ---------------------------
    @app_commands.command(name="reset", description="Weekly reset of characters")
    @requires_st_role()
    async def reset_all(self, interaction: discord.Interaction):
        """Reset all characters (requires ST role)"""
        await interaction.response.defer()
        output_data = []

        try:
            chars = get_all_characters()
            weekly_dta = int(config.get("WEEKLY_DTA", 0))

            for char in chars:
                c = Character(str_uuid=char["uuid"], user_id=char["user_id"], use_cache=True)

                # Apply weekly DTA and reset willpower
                c.total_dta = (c.total_dta or 0) + weekly_dta
                c.curr_dta = (c.curr_dta or 0) + weekly_dta

                entry = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "delta": f"+{weekly_dta}",
                    "reasoning": "Weekly DTA Gain",
                    "result": c.curr_dta,
                    "user": str(interaction.user.id),
                }

                c.dta_log.append(entry)
                c.refetch_data()
                c.reset_willpower()

                # Run blocking Google Sheets write in a thread
                await asyncio.to_thread(c.write_dta_log, interaction)

                c.save_parsed()

                # Build line with character name and mention
                user_mention = f"<@{c.user_id}>"
                output_data.append(f"- **{c.name}** ({user_mention})")

            # Build announcement message
            char_list_text = "\n".join(output_data) if output_data else "No characters found."
            message = (
                "## Announcement\n"
                f"The weekly reset of characters has been completed.\n"
                f"The following characters have gained **{weekly_dta} weekly DTA**:\n\n"
                f"{char_list_text}"
            )

            await interaction.followup.send(message)

        except Exception as e:
            logger.exception(f"[RESET] Error during weekly reset: {e}")
            await interaction.followup.send(f"Error occurred: {e}", ephemeral=True)

    # ---------------------------
    # Update Sheets (ST Only)
    # ---------------------------
    @app_commands.command(name="update-sheets", description="Update the Reference Sheets in player Google Sheets")
    @requires_st_role()
    async def update_sheets(self, interaction: discord.Interaction):
        """Update the reference sheets in all approved Google Sheets"""
        await interaction.response.defer(ephemeral=True)

        try:
            base_url = config.get("BASE_SHEET")
            if not base_url:
                await interaction.followup.send("BASE_SHEET is not configured in .env", ephemeral=True)
                return

            client = get_client()
            base_spreadsheet = client.open_by_url(base_url)
            base_worksheets = base_spreadsheet.worksheets()
            logger.info(f"[SHEETS] Loaded base sheet with {len(base_worksheets)} tabs")

            characters = get_all_characters()
            updated_count = 0

            for char_data in characters:
                char = Character(str_uuid=char_data["uuid"], user_id=char_data["user_id"], use_cache=True)
                sheet_url = char.SHEET_URL
                if not sheet_url:
                    logger.warning(f"[SHEETS] No sheet URL for character {char.name}")
                    continue

                try:
                    player_spreadsheet = await asyncio.to_thread(client.open_by_url, sheet_url)
                    player_tabs = {ws.title: ws for ws in await asyncio.to_thread(player_spreadsheet.worksheets)}

                    logger.info(f"[SHEETS] --- Updating {char.name}'s sheet ---")

                    for base_ws in base_worksheets:
                        tab_name = base_ws.title
                        if tab_name in EXCLUDED_TABS:
                            logger.debug(f"[SHEETS] Skipping excluded tab: {tab_name}")
                            continue

                        target_ws = player_tabs.get(tab_name)
                        if not target_ws:
                            logger.warning(f"[SHEETS] Player sheet missing tab '{tab_name}' ({char.name})")
                            continue

                        values = await asyncio.to_thread(base_ws.get_all_values)
                        if values:
                            logger.info(f"[SHEETS] Updating tab '{tab_name}' for {char.name}")
                            await asyncio.to_thread(target_ws.clear)
                            await asyncio.to_thread(target_ws.update, "A1", values)

                    updated_count += 1
                    logger.info(f"[SHEETS] Finished updating sheet for {char.name}")

                except Exception as e:
                    logger.error(f"[SHEETS] Failed to update {char.name}: {e}")

            await interaction.followup.send(
                f"Synced base sheet to {updated_count} character sheets (excluding: {', '.join(EXCLUDED_TABS)}).",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(f"[SHEETS] Update sheets error: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)

    # ---------------------------
    # Resync Slash Commands (Admin Only)
    # ---------------------------
    @app_commands.command(name="resync", description="Resync slash commands with Discord (admin only).")
    @requires_st_role()
    async def resync(self, interaction: discord.Interaction):
        """Resync all slash commands with Discord."""
        await interaction.response.defer(ephemeral=True)

        try:
            synced = await self.bot.tree.sync()
            logger.info(f"Slash commands resynced successfully ({len(synced)} commands).")
            await interaction.followup.send(f"Commands resynced successfully. ({len(synced)} commands total.)", ephemeral=True)
        except Exception as e:
            logger.exception(f"Failed to sync commands: {e}")
            await interaction.followup.send(f"Failed to sync commands: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ST(bot))
