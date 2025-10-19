import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import asyncio
import logging

from libs.character import Character
from libs.help import get_dta_help_embed

logger = logging.getLogger(__name__)


class DTA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Registered DTA Cog")

    dta = app_commands.Group(
        name="dta",
        description="All DTA related commands"
    )

    # ---------------------------
    # /dta log
    # ---------------------------
    @dta.command(name="log", description="View your current DTA log.")
    async def dta_log(self, interaction: discord.Interaction):
        """Display the DTA log for the user's character in a formatted table."""
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

            embed = discord.Embed(
                title=f"DTA Log — {char.name}",
                description=f"**Current DTA:** {char.curr_dta}\n**Total DTA:** {char.total_dta}",
                color=discord.Color.blurple()
            )
            embed.set_footer(text="Most recent entries last")

            log_entries = getattr(char, "dta_log", []) or []
            if not log_entries:
                embed.add_field(
                    name="No Entries",
                    value="This character has no DTA log entries yet.",
                    inline=False
                )
            else:
                # Sort by timestamp ascending
                sorted_log = sorted(log_entries, key=lambda x: x.get("timestamp", ""))

                # Build table
                header = f"{'Date':<12} | {'Δ':<6} | {'Result':<7} | {'Reason':<30}"
                separator = "-" * len(header)
                lines = [header, separator]

                for entry in sorted_log:
                    try:
                        ts = datetime.fromisoformat(entry["timestamp"])
                        formatted_date = ts.strftime("%d/%m/%Y")
                    except Exception:
                        formatted_date = entry.get("timestamp", "??")

                    delta = entry.get("delta", "")
                    result = str(entry.get("result", ""))
                    reasoning = entry.get("reasoning", "")[:30]
                    line = f"{formatted_date:<12} | {delta:<6} | {result:<7} | {reasoning}"
                    lines.append(line)

                table_text = "\n".join(lines)

                # Split into chunks within Discord’s 1024-char field limit
                while table_text:
                    if len(table_text) <= 1024:
                        embed.add_field(name="Log", value=f"```{table_text}```", inline=False)
                        break
                    split_index = table_text.rfind("\n", 0, 1024)
                    chunk = table_text[:split_index]
                    embed.add_field(name="Log", value=f"```{chunk}```", inline=False)
                    table_text = table_text[split_index + 1:]

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"[DTA LOG] Error loading DTA log for user {user_id}: {e}")
            await interaction.followup.send(
                "An error occurred while retrieving your DTA log.",
                ephemeral=True
            )

    # ---------------------------
    # /dta spend
    # ---------------------------
    @dta.command(name="spend", description="Spend accrued DTA.")
    @app_commands.describe(
        amount="Amount of DTA to spend.",
        reason="Reason for spending."
    )
    async def spend_dta(self, interaction: discord.Interaction, amount: int, reason: str):
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

            if amount <= 0:
                await interaction.followup.send("Amount must be greater than 0.", ephemeral=True)
                return

            if char.curr_dta < amount:
                await interaction.followup.send(
                    f"Not enough DTA points (you currently have {char.curr_dta}).",
                    ephemeral=True
                )
                return

            if not hasattr(char, "dta_log"):
                char.dta_log = []

            char.curr_dta -= amount

            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "delta": f"-{amount}",
                "reasoning": reason,
                "result": char.curr_dta,
                "user": user_id,
            }

            char.dta_log.append(entry)

            # Handle synchronous vs async safely
            try:
                result = await char.write_dta_log(ctx=interaction)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"[DTA SPEND] Write error: {e}")

            char.save_parsed()
            await interaction.followup.send(f"Spent {amount} DTA on '{reason}'. Log updated.", ephemeral=True)
            logger.info(f"[DTA SPEND] {user_id} spent {amount} DTA ({char.name}) for: {reason}")

        except Exception as e:
            logger.exception(f"[DTA SPEND] Error for user {user_id}: {e}")
            await interaction.followup.send("An error occurred while spending DTA.", ephemeral=True)

    # ---------------------------
    # /dta sync
    # ---------------------------
    @dta.command(name="sync", description="Upload your DTA log to the Google Sheet.")
    async def sync(self, interaction: discord.Interaction):
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

            # Handle sync safely for both async/sync versions
            try:
                result = await char.write_dta_log(ctx=interaction)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.warning(f"[DTA SYNC] Write error: {e}")

            await interaction.followup.send("DTA log synced successfully with the sheet.", ephemeral=True)
            logger.info(f"[DTA SYNC] Synced DTA log for {user_id} ({char.name}).")

        except Exception as e:
            logger.exception(f"[DTA SYNC] Error for user {user_id}: {e}")
            await interaction.followup.send("An error occurred while syncing the DTA log.", ephemeral=True)


# ---------------------------
# Cog Setup Function
# ---------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(DTA(bot))
