import discord
from discord.ext import commands
from discord import app_commands

class SceneTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered SceneTracker")

    scene_group = app_commands.Group(name="scene", description="All commands for scenes")

    @scene_group.command(name="create", description="Create a new scene")
    async def create(self, interaction: discord.Interaction, name: str):
        await interaction.response.send_message(f"Created scene: **{name}**")

    @scene_group.command(name="list", description="List all active scenes")
    async def list(self, interaction: discord.Interaction):
        await interaction.response.send_message("Here's a list of scenes...")

    @scene_group.command(name="end", description="End a scene by its ID")
    async def end(self, interaction: discord.Interaction, scene_id: int):
        await interaction.response.send_message(f"Scene #{scene_id} has been ended.")

    @scene_group.command(name="add", description="Add someone to the current scene")
    async def add(self, interaction:discord.Interaction, id:str):
        await interaction.response.send_message(f"Created scene: **{id}**")
