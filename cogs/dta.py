from discord.ext import commands
from discord import app_commands
import discord
from libs.character import *
from cogs.character import *
class DTA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered DTA")
        
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

        
    dta = app_commands.Group(
        name="dta", description="all commands linked to DTA"
    )

    
    @dta.command(name="log", description="See the current DTA Log for a character")
    async def dta_log(self, interaction: discord.Interaction, name: str):
        """Display the DTA log for the specified character in a table format."""
        await interaction.response.defer()
        user_id = str(interaction.user.id)

        try:
            char = Character.load_by_name(name, user_id)
            if not char:
                await interaction.followup.send(f"No character named `{name}` found.")
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
                # Sort by timestamp, newest first
                sorted_log = sorted(
                    char.dta_log,
                    key=lambda x: x.get("timestamp", ""),
                    reverse=False
                )

                # Table header
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
                    reasoning = entry.get("reasoning", "")[:40]  # truncate if long
                    result = str(entry.get("result", ""))

                    line = f"{formatted_date:<12} | {delta:<5} | {result:<6} | {reasoning[:16]}"
                    lines.append(line)

                # Join into code block, chunk if too long
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
            logger.warning(f"[DTA LOG] Error loading DTA log for '{name}' (user {user_id}): {e}")
            await interaction.followup.send(
                "An error occurred while retrieving the DTA log.", ephemeral=True
        )



    @dta_log.autocomplete("name")
    async def log_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete character names for the DTA log command."""
        return await self._character_name_autocomplete(interaction, current)
    
    @dta.command(name="spend", description="Spend accrued DTA")
    async def spend_dta(self, interaction: discord.Interaction, name: str, amount: int, reason: str):
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)

            amount = abs(amount)

            if not char:
                await interaction.followup.send(
                    f"No character named `{name}` found.", ephemeral=True
                )
                return

            if char.curr_dta < amount:
                await interaction.followup.send(
                    f"Not enough DTA points to spend (currently {char.curr_dta})"
                )
                return
                
            if not hasattr(char, "dta_log"):
                char.dta_log = []
                
            char.curr_dta =char.curr_dta - amount
            
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "delta": f"-{amount}",
                "reasoning": reason,
                "result": char.curr_dta,
                "user": str(interaction.user.id),
            }
            
            char.dta_log.append(entry)
            char.write_dta_log(ctx=interaction)
            char.save_parsed()
            await interaction.followup.send("Done!")

        except Exception as e:
            logger.warning(f"Error loading character '{name}' for user {user_id}: {e}")
    
    @spend_dta.autocomplete("name")
    async def spend_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)
    
    @dta.command(name="sync", description="Upload DTA to sheet")
    async def sync(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)
            char.write_dta_log(ctx=interaction)
            await interaction.followup.send("Done!")

        except Exception as e:
            logger.warning(f"Error loading character '{name}' for user {user_id}: {e}")
    
    @sync.autocomplete("name")
    async def sync_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)