import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
import logging
import uuid
import gspread  # for catching gspread.exceptions.APIError

from libs.character import Character
from libs.personas import (
    generate_default_header,
)
from libs.sheet_loader import get_client
from libs.database_loader import list_characters_for_user, create_or_update_persona, update_persona_name_by_old_name

logger = logging.getLogger(__name__)


class CharacterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logger.info("Character Cog registered")

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

            # Check if the user already has a character
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

            # Build Character from sheet
            char = Character(user_id=user_id, SHEET_URL=url)
            char.reset_temp()
            logger.info("Character fetched from sheet")

            # Persist character (fail if already exists)
            saved = char.save_parsed(update=False)
            if saved == -1:
                await interaction.followup.send("Character already saved!", ephemeral=True)
                return

            # Create a default persona for this character
            try:
                # Safe keyword: first 4 letters of name, or fallback to UUID prefix
                base_keyword = (char.name or char.uuid or "pc")[:4]
                keyword = base_keyword.lower().replace(" ", "")

                persona_uuid = str(uuid.uuid4())
                # generate_default_header usually expects dict-like character data
                header = generate_default_header(char.to_dict() if hasattr(char, "to_dict") else char)

                # DB function signature: uuid, user_id, header, keyword, image
                create_or_update_persona(
                    uuid=persona_uuid,
                    user_id=user_id,
                    header=header,
                    keyword=keyword,
                    image=None,
                )
                logger.info(
                    f"Persona created for character {char.name} ({char.uuid}) -> Persona ID: {persona_uuid}"
                )
            except Exception as e:
                logger.error(f"Failed to create persona for {getattr(char, 'uuid', '?')}: {e}")
                await interaction.followup.send(
                    f"Character saved, but there was an error creating the persona: `{e}`",
                    ephemeral=True
                )
                return

            # Nickname
            base_username = interaction.user.name
            playername = (char.player_name or "").strip()
            new_nick = (
                f"{char.name} || {base_username}"
                if playername in ("Player Name", "")
                else f"{char.name} || {playername}"
            )

            # Starting blood entry/log
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "delta": char.max_blood,
                "comment": "Starting Blood",
                "before": 0,
                "result": char.max_blood,
                "user": user_id,
            }
            try:
                char.curr_blood = char.max_blood
                if not hasattr(char, "blood_log") or char.blood_log is None:
                    char.blood_log = []
                char.blood_log.append(entry)
                char.save_parsed()
            except Exception as e:
                logger.warning(f"Failed to write starting blood entry for {char.name}: {e}")

            # Assign roles & nickname
            message = ""
            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    # Assign roles if your role assignment helper is available
                    # await assign_roles_for_character(interaction.user, char)
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
            logger.exception("Error during /character init")
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
            page1.add_field(name="\u200b", value="\u200b", inline=True)
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
                if not hasattr(char, "abilities") or cat not in char.abilities:
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
            has_rituals = hasattr(char, "rituals") and bool(char.rituals)
            has_paths = hasattr(char, "magic_paths") and any((p.get('level') or 0) != 0 for p in (char.magic_paths or []))
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
                    all_sorc = [r.get('sorc_type', 'Rituals') for r in char.rituals]
                    sorc_types = sorted(set(all_sorc))

                    for sorc in sorc_types:
                        rituals = [r for r in char.rituals if r.get('sorc_type') == sorc]
                        rituals.sort(key=lambda r: r.get('level', 0))

                        rituals_text = "\n".join(
                            f"{r.get('name', 'Unknown')} _(Lvl {r.get('level', '?')})_"
                            for r in rituals
                        )
                        if len(rituals_text) > 1024:
                            rituals_text = rituals_text[:1021] + "..."

                        page3.add_field(
                            name=f"{sorc} Rituals",
                            value=rituals_text or "None available.",
                            inline=False
                        )
                else:
                    page3.add_field(name="Rituals", value="None available.", inline=False)

                page3.set_footer(text=f"User: {interaction.user.display_name}")

            # === PAGINATION VIEW ===
            class CharacterView(discord.ui.View):
                def __init__(self, has_page3: bool):
                    super().__init__(timeout=120)
                    self.has_page3 = has_page3

                @discord.ui.button(label="Page 1", style=discord.ButtonStyle.primary, disabled=True)
                async def page1_button(self, i2: discord.Interaction, b: discord.ui.Button):
                    self.page1_button.disabled = True
                    self.page2_button.disabled = False
                    if self.has_page3 and hasattr(self, "page3_button"):
                        self.page3_button.disabled = False
                    await i2.response.edit_message(embed=page1, view=self)

                @discord.ui.button(label="Page 2", style=discord.ButtonStyle.primary)
                async def page2_button(self, i2: discord.Interaction, b: discord.ui.Button):
                    self.page1_button.disabled = False
                    self.page2_button.disabled = True
                    if self.has_page3 and hasattr(self, "page3_button"):
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
            logger.exception("Error showing character")
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # ---------------------------
    # Resync Character
    # ---------------------------
    @character.command(name="resync", description="Resync your character and linked persona")
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

            # Store old name before refetching
            old_name = char.name

            # Refresh character data (pulls in the new name)
            char.refetch_data()

            # Update nickname
            base_username = interaction.user.name
            playername = (char.player_name or "").strip()
            new_nick = (
                f"{char.name} || {base_username}"
                if playername in ("Player Name", "")
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

            # Update linked persona name if it matches the old character name
            try:
                update_persona_name_by_old_name(user_id, old_name, char.name)
            except Exception as e:
                logger.warning(f"Persona name update failed: {e}")

            # Reassign roles if needed
            try:
                # await assign_roles_for_character(interaction.user, char)
                pass
            except Exception as e:
                logger.warning(f"Role assignment failed during resync: {e}")

            await interaction.followup.send("Resynced successfully!", ephemeral=True)

        except Exception as e:
            logger.exception("Error during character resync")
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # ---------------------------
    # Adjust Blood
    # ---------------------------
    @character.command(name="adjust-blood", description="Adjust your character's blood pool manually.")
    @app_commands.describe(
        amount="Positive or negative number (e.g., 2 to gain, -3 to lose)",
        reason="Reason for adjustment"
    )
    async def adjust_blood(self, interaction: discord.Interaction, amount: int, reason: str):
        """Manually adjust the blood pool and record in the blood log."""
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)
        try:
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.followup.send("You don't have a character registered yet.", ephemeral=True)
                return

            before = char.curr_blood
            after = max(0, min(char.max_blood, before + amount))

            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "delta": f"{'+' if amount > 0 else ''}{amount}",
                "comment": reason or "Manual Adjustment",
                "before": before,
                "result": after,
                "user": user_id,
            }

            char.curr_blood = after
            if not hasattr(char, "blood_log") or char.blood_log is None:
                char.blood_log = []
            char.blood_log.append(entry)
            char.save_parsed()

            await interaction.followup.send(
                f"Blood adjusted by {amount}. Current pool: {after}/{char.max_blood}.",
                ephemeral=True
            )

        except Exception as e:
            logger.exception(f"[ADJUST BLOOD] Error for {user_id}: {e}")
            await interaction.followup.send(f"Error adjusting blood: {e}", ephemeral=True)


    # ---------------------------
    # Hunt Command
    # ---------------------------
    @character.command(name="hunt", description="Hunt for blood using a dice roll expression.")
    @app_commands.describe(
        roll_str="Dice expression or macro (e.g. Wits+Streetwise+2)",
        difficulty="Difficulty of the hunt (default 6)",
        comment="Optional description for the roll"
    )
    async def hunt(self, interaction: discord.Interaction, roll_str: str, difficulty: int = 6, comment: str = "Hunting"):
        """Perform a hunting roll; gain blood equal to successes."""
        from libs.roller import process_willpower, resolve_dice_pool, roll_dice, build_roll_embed
        await interaction.response.defer()

        user_id = str(interaction.user.id)
        try:
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.followup.send("You don't have a character registered yet.", ephemeral=True)
                return

            # Expand any macros defined on the character
            macros = getattr(char, "macros", {}) or {}
            expanded_str = roll_str
            for macro_name, macro_value in macros.items():
                if macro_name.lower() in expanded_str.lower():
                    expanded_str = expanded_str.replace(macro_name, macro_value)

            # Process Willpower if present
            expanded_str, wp_used = process_willpower(expanded_str, char)

            # Resolve pool
            total_pool, spec_used, specs_applied = resolve_dice_pool(expanded_str, char)
            if total_pool == -1:
                await interaction.followup.send(
                    "Invalid dice expression. Check syntax or traits.",
                    ephemeral=True
                )
                return

            # Roll dice
            formatted, successes, botch, ones_count = roll_dice(total_pool, spec_used, difficulty, return_ones=True)

            # Apply WP success if used
            if wp_used:
                if ones_count > 0:
                    ones_count -= 1
                else:
                    successes += 1
                    formatted.append("*WP*")

            # Build roll embed
            embed = build_roll_embed(
                interaction,
                total_pool,
                difficulty,
                successes,
                botch,
                formatted,
                specs_applied,
                expanded_str,
                comment,
                wp_used
            )

            # Apply results to blood pool
            gained = max(0, successes)
            before = char.curr_blood
            after = min(char.max_blood, before + gained)

            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "delta": f"+{gained}",
                "comment": f"Hunt Roll ({roll_str})",
                "before": before,
                "result": after,
                "user": user_id,
            }

            char.curr_blood = after
            if not hasattr(char, "blood_log") or char.blood_log is None:
                char.blood_log = []
            char.blood_log.append(entry)
            char.save_parsed()

            # Add blood info to embed
            embed.add_field(
                name="Hunt Result",
                value=f"Successes: {successes}\nBlood gained: {gained}\nCurrent Pool: {after}/{char.max_blood}",
                inline=False
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"[HUNT] Error for {user_id}: {e}")
            await interaction.followup.send(f"Error during hunt: {e}", ephemeral=True)


    # ---------------------------
    # Blood Log Viewer
    # ---------------------------
    @character.command(name="blood-log", description="View your character's blood pool log.")
    async def blood_log(self, interaction: discord.Interaction):
        """Display a formatted log of all blood changes."""
        await interaction.response.defer(ephemeral=True)
        user_id = str(interaction.user.id)

        try:
            char = Character.load_for_user(user_id)
            if not char:
                await interaction.followup.send("You don't have a character registered yet.", ephemeral=True)
                return

            log_entries = getattr(char, "blood_log", []) or []
            embed = discord.Embed(
                title=f"Blood Log — {char.name}",
                description=f"**Current Blood:** {char.curr_blood}/{char.max_blood}",
                color=discord.Color.dark_red()
            )
            embed.set_footer(text="Most recent entries last")

            if not log_entries:
                embed.add_field(name="No Entries", value="No blood log entries yet.", inline=False)
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            # Sort oldest → newest
            sorted_log = sorted(log_entries, key=lambda x: x.get("timestamp", ""), reverse=False)

            header = f"{'Date':<12} | {'Δ':<5} | {'Result':<6} | {'Reason':<18}"
            separator = "-" * len(header)
            lines = [header, separator]

            for entry in sorted_log:
                try:
                    ts = datetime.fromisoformat(entry.get("timestamp", ""))
                    formatted_date = ts.strftime("%d/%m/%Y")
                except Exception:
                    formatted_date = entry.get("timestamp", "")
                delta = entry.get("delta", "")
                result = str(entry.get("result", ""))
                comment = (entry.get("comment", "") or "")[:18]
                line = f"{formatted_date:<12} | {delta:<5} | {result:<6} | {comment:<18}"
                lines.append(line)

            # Handle embed field chunking
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

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"[BLOOD LOG] Error for {user_id}: {e}")
            await interaction.followup.send(f"Error retrieving blood log: {e}", ephemeral=True)



# ---------------------------
# Cog Setup Function
# ---------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterCog(bot))
