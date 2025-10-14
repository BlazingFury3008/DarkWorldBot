import discord
from discord.ext import commands
from discord import app_commands, Role
from libs.character import *
from libs.macro import *
from libs.role import *
from libs.roller import process_willpower, resolve_dice_pool, roll_dice, build_roll_embed, handle_botch_mention
from bot import config
from libs.sheet_loader import *
import aiohttp

import ast
from datetime import datetime

import logging
logger = logging.getLogger(__name__)


class CharacterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Diceroller Cog registered")

    # ---------------------------
    # Group Definition
    # ---------------------------
    character = app_commands.Group(
        name="character", description="All character commands"
    )

    # ---------------------------
    # Sheet Permission Check
    # ---------------------------
    async def _sheet_allows_link_edit(self, url: str) -> bool:
        """
        Attempts to write 'ST Verification' into A1 of the sheet to verify
        that 'Anyone with the link can edit' is enabled.
        Returns True if successful, False otherwise.
        """
        try:
            client = get_client()

            spreadsheet = client.open_by_url(url)
            worksheet = spreadsheet.get_worksheet(0)  # first worksheet

            worksheet.update_acell("A1", "ST Verification")
            logger.debug(f"[SHEET CHECK] Successfully wrote to A1 for {url}")
            return True

        except gspread.exceptions.APIError as e:
            logger.debug(f"[SHEET CHECK] APIError: {e}")
            return False
        except Exception as e:
            logger.error(f"[SHEET CHECK] Unexpected error: {e}")
            return False

    # ---------------------------
    # Init Character
    # ---------------------------
    @character.command(name="init", description="Add a character")
    async def init(self, interaction: discord.Interaction, url: str):
        """Initialise a character into the database (one per user)"""
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)

            # ✅ Check if the user already has a character
            existing_chars = list_characters_for_user(user_id) or []
            if len(existing_chars) > 0:
                await interaction.followup.send(
                    "You already have a character registered. "
                    "You must delete it before adding another.",
                    ephemeral=True
                )
                return

            if not await self._sheet_allows_link_edit(url):
                await interaction.followup.send(
                    "The provided Google Sheet is not shared with 'Anyone with the link can edit'. "
                    "Please update the sharing settings and try again.",
                    ephemeral=True
                )
                return

            char = Character(user_id=user_id, SHEET_URL=url)
            char.reset_temp()
            logger.info("Character Fetched")

            keyword = (char.name or char.uuid).lower().replace(" ", "")
            val = char.save_parsed(keyword=keyword, update=False)
            if val == -1:
                await interaction.followup.send("Character already saved!", ephemeral=True)
                return

            base_username = interaction.user.name
            playername = char.player_name or ""
            new_nick = (
                f"{char.name} || {base_username}"
                if playername.strip() in ("Player Name", "")
                else f"{char.name} || {playername}"
            )

            # Starting blood entry
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "delta": char.max_blood,
                "comment": "Starting Blood",
                "before": 0,
                "result": char.max_blood,
                "user": user_id,
            }
            char.curr_blood = char.max_blood
            char.blood_log.append(entry)
            char.save_parsed()

            # Assign roles & nickname
            message = ""
            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    await assign_roles_for_character(interaction.user, char)
                    await member.edit(nick=new_nick)
                except discord.Forbidden:
                    message = "Character saved, but I don't have permission to change your nickname."

            await interaction.followup.send(
                f"Saved and set nickname to **{new_nick}**\n{message}",
                ephemeral=True
            )

        except ValueError as ve:
            await interaction.followup.send(str(ve), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`",
                ephemeral=True
            )

    # ---------------------------
    # Show Character
    # ---------------------------
    @character.command(name="show", description="See the overview of your character")
    async def show(self, interaction: discord.Interaction):
        """Show details of the user's single saved character"""
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.followup.send(
                    "You don't have a character registered yet.", ephemeral=True
                )
                return

            # === PAGE 1 ===
            page1 = discord.Embed(
                title=f"{char.name or 'Unknown'}",
                description=f"Player: {char.player_name or 'Unknown'}",
                color=discord.Color.dark_red(),
            )
            page1.add_field(name="Clan", value=char.clan or "Unknown", inline=True)
            page1.add_field(name="Generation", value=str(char.generation or "?"), inline=True)
            page1.add_field(name="Sect", value=char.sect or "Unknown", inline=True)

            page1.add_field(name="Concept", value=char.concept or "Unknown", inline=False)
            page1.add_field(
                name="Nature / Demeanor",
                value=f"{char.nature or '?'} / {char.demeanor or '?'}",
                inline=False,
            )

            page1.add_field(
                name="Willpower",
                value=f"{char.curr_willpower}/{char.max_willpower}",
                inline=True,
            )
            page1.add_field(name="", value="", inline=True)
            page1.add_field(
                name="Blood Pool",
                value=f"{char.curr_blood}/{char.max_blood} (Per Turn: {char.blood_per_turn})",
                inline=True,
            )

            # Attributes
            if char.attributes and len(char.attributes) >= 9:
                physical = char.attributes[0:3]
                social = char.attributes[3:6]
                mental = char.attributes[6:9]

                def format_attr_block(block):
                    return "\n".join(f"**{a['name']}** {a['value']}" for a in block)

                page1.add_field(name="Physical", value=format_attr_block(physical), inline=True)
                page1.add_field(name="Social", value=format_attr_block(social), inline=True)
                page1.add_field(name="Mental", value=format_attr_block(mental), inline=True)

            # Abilities
            ability_order = [
                ("Talents", "Talents"),
                ("Skills", "Skills"),
                ("Knowledges", "Knowledges"),
                ("Hobby Talents", "Hobby Talents"),
                ("Professional Skill", "Professional Skill"),
                ("Expert Knowledge", "Expert Knowledge"),
            ]

            def format_abilities(cat):
                if cat not in char.abilities:
                    return None
                entries = [f"**{a['name']}** {a['value']}" for a in char.abilities[cat] if a['value'] > 0]
                return "\n".join(entries) if entries else None

            for cat, display in ability_order:
                text = format_abilities(cat)
                page1.add_field(name=display, value=text or "—", inline=True)

            page1.set_footer(text=f"User: {interaction.user.display_name}")

            # === PAGE 2 ===
            page2 = discord.Embed(
                title=f"{char.name or 'Unknown'}",
                description="Disciplines, Backgrounds, Merits, Flaws, Virtues, Path",
                color=discord.Color.dark_red(),
            )

            if char.disciplines:
                disc_text = "\n".join(f"**{d['name']}** {d['value']}" for d in char.disciplines)
                page2.add_field(name="Disciplines", value=disc_text[:1024], inline=False)

            if char.backgrounds:
                back_text = "\n".join(f"**{b['name']}** {b['value']}" for b in char.backgrounds)
                page2.add_field(name="Backgrounds", value=back_text[:1024], inline=True)

            if char.merits:
                merits_text = "\n".join(f"{m['name'].split('(')[0]} ({m['rating']}pt)" for m in char.merits)
                page2.add_field(name="Merits", value=merits_text[:1024], inline=True)

            if char.flaws:
                flaws_text = "\n".join(f"{f['name'].split('(')[0]} ({f['rating']}pt)" for f in char.flaws)
                page2.add_field(name="Flaws", value=flaws_text[:1024], inline=True)

            if hasattr(char, "virtues") and char.virtues:
                virtues_text = "\n".join(f"**{v['name']}** {v['value']}" for v in char.virtues)
                page2.add_field(name="Virtues", value=virtues_text, inline=True)

            if hasattr(char, "path") and char.path:
                page2.add_field(
                    name="Path",
                    value=f"**{char.path['name']}** {char.path['value']}",
                    inline=True,
                )

            page2.set_footer(text=f"User: {interaction.user.display_name}")

            # === PAGE 3 ===
            has_rituals = hasattr(char, "rituals") and char.rituals
            has_paths = hasattr(char, "magic_paths") and any(p['level'] != 0 for p in char.magic_paths or [])
            page3 = None
            if has_rituals or has_paths:
                page3 = discord.Embed(
                    title=f"{char.name or 'Unknown'}",
                    description="Rituals & Sorcery Paths",
                    color=discord.Color.dark_red(),
                )
                if has_paths:
                    paths_text = "\n".join(
                        f"**{p['name'].split('(')[0]}** {p['level']}" for p in char.magic_paths if p['level'] != 0
                    )
                    page3.add_field(name="Paths", value=paths_text[:1024], inline=False)

                if has_rituals:
                    rituals_text = "\n".join(
                        f"**{r['name']}** (Lvl {r['level']})" for r in char.rituals
                    )
                    page3.add_field(name="Rituals", value=rituals_text[:1024], inline=False)

                page3.set_footer(text=f"User: {interaction.user.display_name}")

            # Pagination
            class CharacterView(discord.ui.View):
                def __init__(self, has_page3: bool):
                    super().__init__(timeout=120)
                    self.has_page3 = has_page3

                @discord.ui.button(label="Page 1", style=discord.ButtonStyle.primary, disabled=True)
                async def page1_button(self, i2: discord.Interaction, b: discord.ui.Button):
                    self.page1_button.disabled = True
                    self.page2_button.disabled = False
                    if self.has_page3:
                        self.page3_button.disabled = False
                    await i2.response.edit_message(embed=page1, view=self)

                @discord.ui.button(label="Page 2", style=discord.ButtonStyle.primary)
                async def page2_button(self, i2: discord.Interaction, b: discord.ui.Button):
                    self.page1_button.disabled = False
                    self.page2_button.disabled = True
                    if self.has_page3:
                        self.page3_button.disabled = False
                    await i2.response.edit_message(embed=page2, view=self)

                if has_rituals or has_paths:
                    @discord.ui.button(label="Page 3", style=discord.ButtonStyle.primary)
                    async def page3_button(self, i2: discord.Interaction, b: discord.ui.Button):
                        self.page1_button.disabled = False
                        self.page2_button.disabled = False
                        self.page3_button.disabled = True
                        await i2.response.edit_message(embed=page3, view=self)

            view = CharacterView(page3 is not None)
            await interaction.followup.send(embed=page1, view=view, ephemeral=True)

        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # ---------------------------
    # Resync Character
    # ---------------------------
    @character.command(name="resync", description="Resync your character")
    async def resync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.followup.send(
                    "You don't have a character to resync.", ephemeral=True
                )
                return

            char.refetch_data()

            base_username = interaction.user.name
            playername = char.player_name or ""
            new_nick = (
                f"{char.name} || {base_username}"
                if playername.strip() in ("Player Name", "")
                else f"{char.name} || {playername}"
            )

            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    await member.edit(nick=new_nick)
                except discord.Forbidden:
                    await interaction.followup.send(
                        "Character resynced, but I don't have permission to change your nickname.",
                        ephemeral=True
                    )

            await assign_roles_for_character(interaction.user, char)
            await interaction.followup.send("Resynced successfully!", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )
