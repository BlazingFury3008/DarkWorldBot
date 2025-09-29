import discord
from discord.ext import commands
from discord import app_commands
from libs.character import *

class CharacterCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("Registered CharacterCog")

    character = app_commands.Group(name="character", description="All character commands")

    @character.command(name="init", description="Add A Character")
    async def init(self, interaction: discord.Interaction, url: str):
        """Initialise a character into the database"""
        await interaction.response.defer()
        try:
            user_id = str(interaction.user.id)  # ensure string for DB
            char = Character(user_id=user_id, SHEET_URL=url)
            char.save_parsed()

            # Format nickname as "char.name || username"
            base_username = interaction.user.name  # actual username (not display name/nick)
            new_nick = f"{char.name} || {base_username}"

            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    await member.edit(nick=new_nick)
                except discord.Forbidden:
                    await interaction.followup.send(
                        f"Character saved, but I don’t have permission to change your nickname.",
                        ephemeral=True,
                    )
                    return

            await interaction.followup.send(
                f"Saved and set nickname to **{new_nick}**", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )