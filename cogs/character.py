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


    async def _sheet_allows_link_edit(self, url: str) -> bool:
        """
        Attempts to write 'ST Verification' into A1 of the sheet to verify
        that 'Anyone with the link can edit' is enabled.
        Returns True if successful, False otherwise.
        """
        try:
            client = get_client()

            # Open by URL
            spreadsheet = client.open_by_url(url)
            worksheet = spreadsheet.get_worksheet(0)  # first worksheet

            # Attempt to write to A1
            worksheet.update_acell("A1", "ST Verification")
            logger.debug(f"[SHEET CHECK] Successfully wrote to A1 for {url}")
            return True

        except gspread.exceptions.APIError as e:
            # Typically raised if the sheet is not editable by the service account
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
        """Initialise a character into the database"""
        await interaction.response.defer(ephemeral=True)
        try:
            if not await self._sheet_allows_link_edit(url):
                await interaction.followup.send(
                    "The provided Google Sheet is not shared with 'Anyone with the link can edit'. "
                    "Please open the sheet, click Share, select 'Anyone with the link', and set it to Editor. "
                    "Then try again.",
                    ephemeral=True
                 )       
                return     
            user_id = str(interaction.user.id)
            char = Character(user_id=user_id, SHEET_URL=url)
            char.reset_temp()
            logger.info("Character Fetched")
        

            # Generate a keyword (used for Tupper functionality later)
            keyword = (char.name or char.uuid).lower().replace(" ", "")
            val = char.save_parsed(keyword=keyword, update=False)

            if val == -1:
                await interaction.followup.send("Character already saved!", ephemeral=True)
                return

            base_username = interaction.user.name
            playername = char.player_name
            
            if playername.strip() == "Player Name" or playername.strip() == "":
                new_nick = f"{char.name} || {base_username}"
            else:
                new_nick = f"{char.name} || {playername}"

            entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "delta": char.max_blood,
            "comment": "Starting Blood",
            "before": 0,
            "result": char.max_blood,
            "user": str(interaction.user.id),
            }
            char.curr_blood = char.max_blood
            char.blood_log.append(entry)
            char.save_parsed()

            message = ""
            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    await assign_roles_for_character(interaction.user, char)
                    await member.edit(nick=new_nick)
                except discord.Forbidden:
                    message = "Character saved, but I don't have permission to change your nickname."

            await interaction.followup.send(f"Saved and set nickname to **{new_nick}**\n", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    @character.command(name="show", description="See the overview of one of your saved characters")
    @app_commands.describe(name="Pick the character to display")
    async def show(self, interaction: discord.Interaction, name: str):
        """Show details of a saved character across up to 3 pages"""
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)

            if not char:
                await interaction.followup.send(
                    f"No character named `{name}` found.", ephemeral=True
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

            # Willpower / Blood Pool
            page1.add_field(
                name="Willpower",
                value=f"{char.curr_willpower}/{char.max_willpower}",
                inline=True,
            )
            page1.add_field(name="", value="", inline=True, ) # For Formatting
            
            page1.add_field(
                name="Blood Pool",
                value=f"{char.curr_blood}/{char.max_blood} (Per Turn: {char.blood_per_turn})",
                inline=True,
            )

            # === Attributes (3 Columns: Physical, Social, Mental) ===
            if char.attributes and len(char.attributes) >= 9:
                physical = char.attributes[0:3]
                social = char.attributes[3:6]
                mental = char.attributes[6:9]

                def format_attr_block(block):
                    return "\n".join(
                        f"**{a['name']}** {a['value']}"
                        for a in block
                    )

                page1.add_field(name="Physical", value=format_attr_block(physical), inline=True)
                page1.add_field(name="Social", value=format_attr_block(social), inline=True)
                page1.add_field(name="Mental", value=format_attr_block(mental), inline=True)

            # === Abilities (2 Rows × 3 Columns) ===
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
                entries = [
                    f"**{a['name']}** {a['value']}"
                    for a in char.abilities[cat] if a['value'] > 0
                ]
                return "\n".join(entries) if entries else None

            for i, (cat, display) in enumerate(ability_order):
                text = format_abilities(cat)
                if text:
                    page1.add_field(name=display, value=text[:1024], inline=True)
                else:
                    # Add blank field to keep column alignment
                    page1.add_field(name=display, value="—", inline=True)

            page1.set_footer(text=f"User: {interaction.user.display_name}")

            # === PAGE 2 ===
            page2 = discord.Embed(
                title=f"{char.name or 'Unknown'}",
                description="Disciplines, Backgrounds, Merits, Flaws, Virtues, Path",
                color=discord.Color.dark_red(),
            )

            # Disciplines
            disc_text = ""
            if char.disciplines:
                disc_text = "\n".join(f"**{d['name']}** {d['value']}" for d in char.disciplines)
            if disc_text:
                page2.add_field(name="Disciplines", value=disc_text[:1024], inline=False)

            # Backgrounds | Merits | Flaws (3 inline)
            back_text = None
            merits_text = None
            flaws_text = None

            if char.backgrounds:
                back_text = "\n".join(f"**{b['name']}** {b['value']}" for b in char.backgrounds)

            if char.merits:
                merits_text = "\n".join(
                    f"{m['name'].split('(')[0]} ({m['rating']}pt)" for m in char.merits
                )

            if char.flaws:
                flaws_text = "\n".join(
                    f"{f['name'].split('(')[0]} ({f['rating']}pt)" for f in char.flaws
                )

            if back_text:
                page2.add_field(name="Backgrounds", value=back_text[:1024], inline=True)
            if merits_text:
                page2.add_field(name="Merits", value=merits_text[:1024], inline=True)
            if flaws_text:
                page2.add_field(name="Flaws", value=flaws_text[:1024], inline=True)

            # Virtues | Path (2 inline)
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

            # === PAGE 3 (Optional) ===
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

            # === Pagination View ===
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

    @show.autocomplete("name")
    async def show_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)


    # ---------------------------
    # Resync Character
    # ---------------------------
    @character.command(name="resync", description="Resync one of your saved characters")
    @app_commands.describe(name="Pick the character to resync")
    async def resync(self, interaction: discord.Interaction, name: str):
        """Force refresh from Google Sheets"""
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)
            if not char:
                await interaction.followup.send(
                    f"No character named `{name}` found.", ephemeral=True
                )
                return

            char.refetch_data()

            base_username = interaction.user.name
            playername = char.player_name
            
            if playername.strip() == "Player Name" or playername.strip() == "":
                new_nick = f"{char.name} || {base_username}"
            else:
                new_nick = f"{char.name} || {playername}"

            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    await member.edit(nick=new_nick)
                except discord.Forbidden as e:
                    # Print the reason to the console for debugging
                    print(f"[Nickname Change Forbidden] Could not change nickname for {member} ({member.id}): {e}")
                    await interaction.followup.send(
                        "Character resynced, but I don't have permission to change your nickname.",
                        ephemeral=True
                    )
                except discord.HTTPException as e:
                    # Catch other HTTP errors
                    print(f"[Nickname Change HTTP Error] Could not change nickname for {member} ({member.id}): {e}")
                    await interaction.followup.send(
                        "Character resynced, but an error occurred while changing the nickname.",
                        ephemeral=True
                    )

            await assign_roles_for_character(interaction.user, char)

            await interaction.followup.send("Resynced successfully!", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    @resync.autocomplete("name")
    async def resync_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)

    # ---------------------------
    # Keyword Management
    # ---------------------------
    @character.command(name="keyword", description="Edit your character's keyword")
    @app_commands.describe(name="Character to update", new_keyword="New keyword to assign")
    async def keyword(self, interaction: discord.Interaction, name: str, new_keyword: str):
        """Edit the keyword for one of your saved characters"""
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            uuid = get_character_uuid_by_name(user_id, name)
            if not uuid:
                await interaction.followup.send(
                    f"No character named `{name}` found.", ephemeral=True
                )
                return

            updated = update_character_keyword(uuid, user_id, new_keyword.lower())
            if not updated:
                await interaction.followup.send(
                    "Failed to update keyword. Please try again.", ephemeral=True
                )
                return

            await interaction.followup.send(
                f"✅ Keyword for **{name}** updated to **{new_keyword.lower()}**",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    @keyword.autocomplete("name")
    async def keyword_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)

    # ---------------------------
    # Adjust Blood
    # ---------------------------
    @character.command(name="adjust-blood", description="Adjust a character's blood pool (+/-)")
    @app_commands.describe(
        name="Character name",
        amount="Amount of blood to adjust (use negative for spending)",
        comment="Reason for the change (e.g. 'fed from X' or 'used X')"
    )
    async def adjust_blood(self, interaction: discord.Interaction, name: str, amount: int, comment: str):
        await interaction.response.defer(ephemeral=True)

        char_uuid = get_character_uuid_by_name(str(interaction.user.id), name)
        char = Character(str_uuid=char_uuid, user_id=interaction.user.id, use_cache=True)

        # Ensure blood tracking
        if not hasattr(char, "curr_blood") or char.curr_blood is None:
            char.curr_blood = char.max_blood
        if not hasattr(char, "blood_log"):
            char.blood_log = []

        # Apply adjustment
        new_blood = max(0, min(char.max_blood, char.curr_blood + amount))
        delta = new_blood - char.curr_blood

        # Log entry
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "delta": delta,
            "comment": comment,
            "before": char.curr_blood,
            "result": new_blood,
            "user": str(interaction.user.id),
        }
        char.curr_blood = new_blood
        char.blood_log.append(entry)
        char.save_parsed()

        # Hunger Torpor trigger
        if char.curr_blood == 0:
            role_names = config.get("ROLES", [])
            guild_roles: list[Role] = interaction.guild.roles
            mentions = " ".join([r.mention for r in guild_roles if r.name in role_names]) or ""
            await interaction.followup.send(
                f"{mentions} - {char.name} has exerted too much blood and has fallen into **Hunger Torpor**!",
                ephemeral=False,
            )
            return

        await interaction.followup.send(
            f"{char.name} blood adjusted by {delta} ({comment}). "
            f"Current pool: {char.curr_blood}/{char.max_blood}.",
        )

    @adjust_blood.autocomplete("name")
    async def adjust_blood_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)
    
    # ---------------------------
    # Hunt
    # ---------------------------
        
    @character.command(name="hunt", description="Go Hunting")
    @app_commands.describe(
        name="Character name",
        hunt_str="Rolestring for hunting",
        difficulty="Difficulty of the hunting roll",
        comment="Any information needed for/about the hunt"
    )
    async def hunt(self, interaction: discord.Interaction, name: str, hunt_str: str, difficulty: int, comment: str = ""):
        await interaction.response.defer(ephemeral=True)

        try:
            roll_str = hunt_str
            # Load character
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)
            if not char:
                await interaction.followup.send(f"No character named {name} found.", ephemeral=True)
                return

            # Willpower
            roll_str, willpower_used = process_willpower(roll_str, char)

            # Dice pool
            total_pool, spec_used, specs_applied = resolve_dice_pool(roll_str, char)
            if total_pool == -1:
                await interaction.followup.send(
                    "Unable to roll this pool. Check your syntax and try again.",
                    ephemeral=True,
                )
                return

            # Dice roll
            formatted, successes, botch, ones_count = roll_dice(
                total_pool, spec_used, difficulty, return_ones=True
            )

            # Apply Willpower auto-success
            if willpower_used:
                if ones_count > 0:
                    ones_count -= 1
                    logger.debug("[HUNT] Willpower success canceled by a '1'")
                else:
                    successes += 1
                    formatted.append("*WP*")

            # Apply Efficient Digestion if present
            if hasattr(char, "merits") and "Efficient Digestion" in char.merits and successes > 0:
                successes = int(successes * 1.5)
                formatted.append("(×1.5 Efficient Digestion)")

            # Apply blood gain and log it
            if not hasattr(char, "curr_blood") or char.curr_blood is None:
                char.curr_blood = char.max_blood
            if not hasattr(char, "blood_log") or char.blood_log is None:
                char.blood_log = []

            before_blood = char.curr_blood
            char.curr_blood = min(char.max_blood, char.curr_blood + successes)
            gained_blood = char.curr_blood - before_blood

            # Log entry
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "delta": gained_blood,
                "comment": comment or "Hunting",
                "before": before_blood,
                "result": char.curr_blood,
                "user": user_id,
            }
            char.blood_log.append(entry)
            char.save_parsed()

            # Build Embed
            embed = build_roll_embed(
                interaction, total_pool, difficulty, successes, botch,
                formatted, specs_applied, roll_str, comment, willpower_used
            )

            embed.add_field(
                name="Hunting Result",
                value=f"**Blood Gained:** {gained_blood}\n**New Pool:** {char.curr_blood}/{char.max_blood}",
                inline=False
            )
            
           # Botch role ping
            if botch:
                await handle_botch_mention(interaction, char.name)

            # Replace ephemeral with public message
            try:
                await interaction.delete_original_response()
            except Exception:
                pass

            await interaction.channel.send(embed=embed)

            # NO hunger ping

        except ValueError as ve:
            await interaction.followup.send(str(ve), ephemeral=True)
        except Exception as e:
            logger.exception(f"[HUNT] Roll command error: {e}")
            await interaction.followup.send(f"Error: {e}", ephemeral=True)



    @hunt.autocomplete("name")
    async def adjust_blood_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)
    # --------------------------
    # Show Blood Logs
    # --------------------------
    @character.command(name="blood-log", description="Show character blood-log")
    @app_commands.describe(uuid="Character to display")
    async def blood_log(self, interaction: discord.Interaction, uuid: str):
        await interaction.response.defer()
        name = ""
        user_id = ""
        try:
            d = get_character_by_uuid(uuid)
            name = d['name']
            user_id = d['user_id']
            char = Character.load_by_name(name, user_id)
            if not char:
                await interaction.followup.send(f"No character named `{name}` found.")
                return

            if not hasattr(char, "blood_log"):
                char.blood_log = []
                char.save_parsed()

            embed = discord.Embed(
                title=f"Blood Log — {char.name}",
                description=f"**Current Blood:** {char.curr_blood}\n**Total Blood:** {char.max_blood}",
                color=discord.Color.blurple()
            )
            embed.set_footer(text="Most recent entries last")

            if not char.blood_log or len(char.blood_log) == 0:
                embed.add_field(
                    name="No Entries",
                    value="This character has no Blood log entries yet.",
                    inline=False
                )
            else:
                # Sort by timestamp, newest first
                sorted_log = sorted(
                    char.blood_log,
                    key=lambda x: x.get("timestamp", ""),
                    reverse=False
                )

                # Table header
                header = f"{'Date':<12} | {'Δ':<5} | {'Before':<6} | {'After':<6} | {'Comment':<8}"
                separator = "-" * len(header)
                lines = [header, separator]

                for entry in sorted_log:
                    try:
                        ts = datetime.fromisoformat(entry["timestamp"])
                        formatted_date = ts.strftime("%d/%m/%Y")
                    except Exception:
                        formatted_date = entry.get("timestamp", "")

                    delta = entry.get("delta", "")
                    comment = entry.get("comment", "")[:40]  # truncate if long
                    result = str(entry.get("result", ""))
                    before = str(entry.get("before", ""))

                    line = f"{formatted_date:<12} | {delta:<5} | {before:<6} | {result:<6} | {comment[:8]}"
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
            logger.warning(f"[BLOOD LOG] Error loading Blood Log for '{name}' (user {user_id}): {e}")
            await interaction.followup.send(
                "An error occurred while retrieving the Blood Log.", ephemeral=True
        )


    @blood_log.autocomplete("uuid")
    async def blood_log_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete character names"""
        try:
            names = list_all_characters() or []
            logger.debug(f"Autocomplete names for: {names}")
        except Exception as e:
            logger.error(f"Autocomplete error: {e}")
            names = []
        return [
            app_commands.Choice(name=f"{n['name']} | {n['player_name']}", value=n["uuid"])
            for n in names if current.lower() in n['name'].lower()
        ][:25]