import discord
from discord.ext import commands
from discord import app_commands

class Helper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered Helper")

    helper = app_commands.Group(name="helper", description="All helper commands")

    @helper.command(name="resync", description="resync commands")
    async def resync(self, interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.bot.tree.sync()
        print("Commands Synced")
        await interaction.followup.send("Synced Commands", ephemeral=True)