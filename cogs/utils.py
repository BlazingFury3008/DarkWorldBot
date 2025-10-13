import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Utils Cog registered")

    @app_commands.command(name="resync", description="Resync slash commands with Discord")
    async def resync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.bot.tree.sync()
        logger.info("Commands synced")
        await interaction.followup.send(" Synced commands.", ephemeral=True)
        
    