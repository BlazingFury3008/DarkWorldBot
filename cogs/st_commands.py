import ast
from discord.ext import commands
from discord import app_commands
import discord
from libs.character import *
from dotenv import dotenv_values
import asyncio
config = dotenv_values(".env")

import logging

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
    "Your Blood Storage"
    ]

def requires_st_role():
    """Custom check to ensure the user has one of the allowed ST roles."""
    async def predicate(interaction: discord.Interaction) -> bool:
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

    return app_commands.check(predicate)


class ST(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Registered ST Commands")

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

                # ✅ Run blocking Google Sheets write in a thread
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
                            # Log which worksheet is being updated
                            logger.info(f"[SHEETS] Updating tab '{tab_name}' for {char.name}")

                            # Clear & update inside thread to avoid blocking loop
                            await asyncio.to_thread(target_ws.clear)
                            await asyncio.to_thread(target_ws.update, "A1", values)

                    updated_count += 1
                    logger.info(f"[SHEETS] Finished updating sheet for {char.name}")

                except Exception as e:
                    logger.error(f"[SHEETS] Failed to update {char.name}: {e}")

            await interaction.followup.send(
                f" Synced base sheet to {updated_count} character sheets (excluding: {', '.join(EXCLUDED_TABS)}).",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(f"[SHEETS] Update sheets error: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)
