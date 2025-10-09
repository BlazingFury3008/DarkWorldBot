import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)

class Helper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        logger.info("Helper Cog registered")

    helper = app_commands.Group(name="helper", description="All helper commands")

    @app_commands.command(name="resync", description="Resync slash commands with Discord")
    async def resync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.bot.tree.sync()
        logger.info("Commands synced")
        await interaction.followup.send("✅ Synced commands.", ephemeral=True)

    @app_commands.command(name="help", description="Help for all commands available")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            # === PAGE 1: General Commands ===
            page1 = discord.Embed(
                title="DarkWorldBot Help – Page 1",
                description="General commands and basic usage",
                color=discord.Color.blurple(),
            )
            page1.add_field(
                name="/roll",
                value=(
                    "Roll dice using a character's traits or a macro.\n"
                    "Example:\n"
                    "`/roll name:Zayd roll_str:Dexterity+Melee[Swords] difficulty:6`\n\n"
                    "See `/roll-help` for full syntax and explanation."
                ),
                inline=False
            )
            page1.add_field(
                name="/macro",
                value=(
                    "Manage your character's saved macros.\n"
                    "• `/macro new` – Create a new macro.\n"
                    "• `/macro edit` – Edit an existing macro.\n"
                    "• `/macro delete` – Remove a macro.\n\n"
                    "Macros let you save complex roll strings for quick use."
                ),
                inline=False
            )
            page1.set_footer(text="Page 1 • General Commands")

            # === PAGE 2: Character Commands ===
            page2 = discord.Embed(
                title="DarkWorldBot Help – Page 2",
                description="Character commands and utilities",
                color=discord.Color.blurple(),
            )
            page2.add_field(
                name="/character init url:[URL]",
                value=(
                    "Create a character profile from a **Google Sheet** URL (template provided in the Venue Guide). "
                    "This will also set your Discord nickname to match the character and player name."
                ),
                inline=False
            )
            page2.add_field(
                name="/character resync name:[NAME]",
                value=(
                    "Refresh a character's data from the linked Google Sheet. "
                    "Also updates your nickname if it changed in the sheet."
                ),
                inline=False
            )
            page2.add_field(
                name="/character show name:[NAME]",
                value=(
                    "Display your character sheet in a paginated embed. "
                    "Includes Attributes, Abilities, Disciplines, Backgrounds, Merits/Flaws, Rituals, and more."
                ),
                inline=False
            )
            page2.add_field(
                name="/character keyword name:[NAME] new_keyword:[KEYWORD]",
                value=(
                    "Change the **keyword** used for Tupperbot integration. "
                    "Keywords are used for IC posting."
                ),
                inline=False
            )
            page2.add_field(
                name="/character adjust-blood name:[NAME] amount:[±INT] comment:[TEXT]",
                value=(
                    "Adjust a character's **blood pool** by the specified amount. "
                    "Use a negative number to spend blood, or a positive number to add."
                ),
                inline=False
            )
            page2.add_field(
                name="/character blood-log uuid:[UUID]",
                value=(
                    "Display the **blood log** table for a character, showing recent adjustments, timestamps, and reasons."
                ),
                inline=False
            )
            page2.set_footer(text="Page 2 • Character Commands")

            # === PAGE 3: Advanced Features ===
            page3 = discord.Embed(
                title="DarkWorldBot Help – Page 3",
                description="Advanced mechanics and system features",
                color=discord.Color.blurple(),
            )
            page3.add_field(
                name="Botches & Role Mentions",
                value=(
                    "If you roll a **botch** (no successes and at least one 1), the bot will send a public message "
                    "and mention Storyteller/renfield roles defined in the `.env` file under `ROLES`."
                ),
                inline=False
            )
            page3.add_field(
                name="Dice Formatting",
                value=(
                    "• **Bold** = Critical (10 with spec)\n"
                    "• *Italic* = Success\n"
                    "• ~~Strikethrough~~ = Success canceled by 1\n"
                    "• Normal text = Failure\n\n"
                    "Dice are sorted from lowest to highest."
                ),
                inline=False
            )
            page3.set_footer(text="Page 3 • Advanced Features")

            # === Pagination View ===
            class HelpView(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=180)

                @discord.ui.button(label="General", style=discord.ButtonStyle.primary, disabled=True)
                async def page1_button(self, i2: discord.Interaction, b: discord.ui.Button):
                    self.page1_button.disabled = True
                    self.page2_button.disabled = False
                    self.page3_button.disabled = False
                    await i2.response.edit_message(embed=page1, view=self)

                @discord.ui.button(label="Characters", style=discord.ButtonStyle.primary)
                async def page2_button(self, i2: discord.Interaction, b: discord.ui.Button):
                    self.page1_button.disabled = False
                    self.page2_button.disabled = True
                    self.page3_button.disabled = False
                    await i2.response.edit_message(embed=page2, view=self)

                @discord.ui.button(label="Advanced", style=discord.ButtonStyle.primary)
                async def page3_button(self, i2: discord.Interaction, b: discord.ui.Button):
                    self.page1_button.disabled = False
                    self.page2_button.disabled = False
                    self.page3_button.disabled = True
                    await i2.response.edit_message(embed=page3, view=self)

            view = HelpView()
            await interaction.followup.send(embed=page1, view=view, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )