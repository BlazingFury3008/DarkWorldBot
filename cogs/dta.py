from discord.ext import commands
from discord import app_commands
import discord
from libs.character import *
from cogs.character import *
from libs.help import get_dta_help_embed
from datetime import datetime

import logging
logger = logging.getLogger(__name__)

class DTA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Registered DTA")

    dta = app_commands.Group(
        name="dta",
        description="All DTA related commands"
    )

    # ---------------------------
    # /dta log
    # ---------------------------
    @dta.command(name="log", description="See the current DTA Log for your character")
    async def dta_log(self, interaction: discord.Interaction):
        """Display the DTA log for the user's character in a table format."""
        await interaction.response.defer()
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

            if not char.dta_log or len(char.dta_log) == 0:
                embed.add_field(
                    name="No Entries",
                    value="This character has no DTA log entries yet.",
                    inline=False
                )
            else:
                # Sort by timestamp, oldest first
                sorted_log = sorted(
                    char.dta_log,
                    key=lambda x: x.get("timestamp", ""),
                    reverse=False
                )

                header = f"{'Date':<12} | {'Δ':<5} | {'Result':<6} | {'Reason':<16}"
                separator = "-" * len(header)
                lines = [header, separator]

                for entry in sorted_log:
                    try:
                        ts = datetime.fromisoformat(entry["timestamp"])
                        formatted_date = ts.strftime("%d/%m/%Y")
                    except Exception:
                        formatted_date = entry.get("timestamp", "")

                    delta = entry.get("delta", "")
                    reasoning = entry.get("reasoning", "")[:40]
                    result = str(entry.get("result", ""))

                    line = f"{formatted_date:<12} | {delta:<5} | {result:<6} | {reasoning[:16]}"
                    lines.append(line)

                table_text = "\n".join(lines)
                while table_text:
                    if len(table_text) <= 1024:
                        embed.add_field(name="Log", value=f"```{table_text}```", inline=False)
                        break
                    else:
                        split_index = table_text.rfind("\n", 0, 1024)
                        chunk = table_text[:split_index]
                        embed.add_field(name="Log", value=f"```{chunk}```", inline=False)
                        table_text = table_text[split_index + 1:]

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.warning(f"[DTA LOG] Error loading DTA log for user {user_id}: {e}")
            await interaction.followup.send(
                "An error occurred while retrieving the DTA log.",
                ephemeral=True
            )

    # ---------------------------
    # /dta spend
    # ---------------------------
    @dta.command(name="spend", description="Spend accrued DTA")
    @app_commands.describe(
        amount="Amount of DTA to spend",
        reason="Reason for spending"
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

            amount = abs(amount)
            if char.curr_dta < amount:
                await interaction.followup.send(
                    f"Not enough DTA points to spend (currently {char.curr_dta})",
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
            char.write_dta_log(ctx=interaction)
            char.save_parsed()
            await interaction.followup.send("DTA spent and log updated!", ephemeral=True)

        except Exception as e:
            logger.warning(f"[DTA SPEND] Error for user {user_id}: {e}")
            await interaction.followup.send(
                "An error occurred while spending DTA.",
                ephemeral=True
            )

    # ---------------------------
    # /dta sync
    # ---------------------------
    @dta.command(name="sync", description="Upload your DTA log to the sheet")
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

            char.write_dta_log(ctx=interaction)
            await interaction.followup.send("DTA log synced with the sheet!", ephemeral=True)

        except Exception as e:
            logger.warning(f"[DTA SYNC] Error for user {user_id}: {e}")
            await interaction.followup.send(
                "An error occurred while syncing the DTA log.",
                ephemeral=True
            )
