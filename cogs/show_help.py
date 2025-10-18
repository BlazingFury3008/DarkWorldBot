import discord
from discord.ext import commands
from discord import app_commands

from libs.help import (
    get_macro_help_embed,
    get_roll_help_embed,
    get_dta_help_embed,
    get_character_help_embed,
    get_st_help_embed
)

import logging
logger = logging.getLogger(__name__)


# ---------------------------
# Pagination View for General Help
# ---------------------------
class HelpPaginationView(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed], user_id: int):
        super().__init__(timeout=180)
        self.embeds = embeds
        self.index = 0
        self.user_id = user_id

    async def update_message(self, interaction: discord.Interaction):
        """Update the message with the current embed and button states."""
        # Safely update button states
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "Previous":
                    child.disabled = self.index == 0
                elif child.label == "Next":
                    child.disabled = self.index == len(self.embeds) - 1

        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the previous help page."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can't control this menu.", ephemeral=True)
            return

        if self.index > 0:
            self.index -= 1

        await self.update_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to the next help page."""
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("You can't control this menu.", ephemeral=True)
            return

        if self.index < len(self.embeds) - 1:
            self.index += 1

        await self.update_message(interaction)


# ---------------------------
# Help Cog
# ---------------------------
class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Registered Help Cog")

    help = app_commands.Group(
        name="help",
        description="Help commands for using the bot"
    )

    # ---------------------------
    # Individual Help Commands
    # ---------------------------
    @help.command(name="macro", description="Show help for Macros")
    async def macro_help(self, interaction: discord.Interaction):
        embed = get_macro_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @help.command(name="roll", description="Show help for Rolling")
    async def roll_help(self, interaction: discord.Interaction):
        embed = get_roll_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @help.command(name="dta", description="Show help for DTA")
    async def dta_help(self, interaction: discord.Interaction):
        embed = get_dta_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @help.command(name="character", description="Show help for Character Commands")
    async def character_help(self, interaction: discord.Interaction):
        embed = get_character_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @help.command(name="storyteller", description="Show help for Storyteller Commands")
    async def storyteller_help(self, interaction: discord.Interaction):
        embed = get_st_help_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------------------
    # General Help (Pagination)
    # ---------------------------
    @help.command(name="all", description="Show general help with all categories")
    async def general_help(self, interaction: discord.Interaction):
        """Display all help categories in a paginated format."""
        embeds = [
            get_character_help_embed(),
            get_roll_help_embed(),
            get_macro_help_embed(),
            get_dta_help_embed(),
            get_st_help_embed()
        ]

        # Add page numbers
        for idx, embed in enumerate(embeds, start=1):
            embed.set_footer(text=f"Page {idx}/{len(embeds)}")

        view = HelpPaginationView(embeds, interaction.user.id)
        await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Help(bot))
