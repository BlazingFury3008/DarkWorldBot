import discord
from discord.ext import commands
from discord import app_commands
import re

class SceneTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered SceneTracker")

    scene_group = app_commands.Group(name="scene", description="All commands for scenes")

    @scene_group.command(name="create", description="Create a new scene")
    async def create(self, interaction: discord.Interaction, name: str, players: str):
        await interaction.response.defer()

        # Extract all user IDs from the format <@123456789>
        player_mentions = players.split()
        try:
            player_ids = [int(re.findall(r'\d+', mention)[0]) for mention in player_mentions]
        except IndexError:
            await interaction.followup.send("One or more player mentions are not in the correct format.")
            return

        # Gather all member IDs from the guild
        guild_member_ids = {member.id for member in interaction.guild.members}

        # Check for invalid IDs
        for pid in player_ids:
            if pid not in guild_member_ids:
                await interaction.followup.send(f"Player ID {pid} is not a valid guild member.")
                return

        print("All player IDs validated successfully.")

        # If all player ids exist, create scene in database and display a header for the scene
        await interaction.followup.send(f"{name}: \n {players}")

    @scene_group.command(name="list", description="List all active scenes")
    async def list(self, interaction: discord.Interaction):
        await interaction.response.send_message("Here's a list of scenes...")

    @scene_group.command(name="end", description="End a scene by its ID")
    async def end(self, interaction: discord.Interaction, scene_id: int):
        await interaction.response.send_message(f"Scene #{scene_id} has been ended.")

    @scene_group.command(name="add", description="Add someone to the current scene")
    async def add(self, interaction:discord.Interaction, id:str):
        await interaction.response.send_message(f"Created scene: **{id}**")
