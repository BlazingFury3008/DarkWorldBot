import discord
from discord.ext import commands
from discord import app_commands, Role
from libs.character import *
import logging
from bot import config
import ast
from datetime import datetime

logger = logging.getLogger(__name__)


class CharacterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("Registered CharacterCog")

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

    # ---------------------------
    # Init Character
    # ---------------------------
    @character.command(name="init", description="Add a character")
    async def init(self, interaction: discord.Interaction, url: str):
        """Initialise a character into the database"""
        await interaction.response.defer(ephemeral=True)
        try:
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

            # Update user nickname with character
            base_username = interaction.user.name
            new_nick = f"{char.name} || {base_username}"

            message = ""
            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    await member.edit(nick=new_nick)
                except discord.Forbidden:
                    message = "Character saved, but I don't have permission to change your nickname."

            await interaction.followup.send(
                f"Saved and set nickname to **{new_nick}**\n"
                f"Keyword for Tuppers: **{keyword}** \n {message}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    # ---------------------------
    # Show Character
    # ---------------------------
    @character.command(name="show", description="Show one of your saved characters")
    @app_commands.describe(name="Pick the character to display")
    async def show(self, interaction: discord.Interaction, name: str):
        """Show details of a saved character"""
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            char = Character.load_by_name(name, user_id)
            if not char:
                await interaction.followup.send(
                    f"No character named `{name}` found.", ephemeral=True
                )
                return

            # Build character embed
            embed = discord.Embed(
                title=f"{char.name or 'Unknown'}",
                description=f"Player: {char.player_name or 'Unknown'}",
                color=discord.Color.dark_red(),
            )
            embed.add_field(name="Clan", value=char.clan or "Unknown", inline=True)
            embed.add_field(name="Generation", value=str(char.generation or "?"), inline=True)
            embed.add_field(name="Sect", value=char.sect or "Unknown", inline=True)

            embed.add_field(name="Concept", value=char.concept or "Unknown", inline=False)
            embed.add_field(name="Nature/Demeanor",
                            value=f"{char.nature or '?'} / {char.demeanor or '?'}", inline=False)
            embed.add_field(name="Bane", value=char.bane or "None", inline=False)

            embed.add_field(
                name="Willpower",
                value=f"{str(char.curr_willpower or 0)}/{str(char.max_willpower or 0)}",
                inline=True,
            )
            embed.add_field(
                name="Blood Pool",
                value=f"{char.curr_blood or '?'}/{char.max_blood or '?'} "
                      f"(Blood Per Turn: {char.blood_per_turn or '?'})",
                inline=True,
            )

            if char.disciplines:
                disc_text = "\n".join(f"**{d['name']}** {d['value']}" for d in char.disciplines)
                embed.add_field(name="Disciplines", value=disc_text[:1024], inline=False)

            if char.backgrounds:
                back_text = "\n".join(f"**{b['name']}** {b['value']}" for b in char.backgrounds)
                embed.add_field(name="Backgrounds", value=back_text[:1024], inline=False)

            if char.merits:
                merits_text = "\n".join(f"{m['name']} ({m['rating']}pt)" for m in char.merits)
                embed.add_field(name="Merits", value=merits_text[:1024], inline=False)

            if char.flaws:
                flaws_text = "\n".join(f"{f['name']} ({f['rating']}pt)" for f in char.flaws)
                embed.add_field(name="Flaws", value=flaws_text[:1024], inline=False)

            embed.set_footer(text=f"User: {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

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
            new_nick = f"{char.name} || {base_username}"

            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    await member.edit(nick=new_nick)
                except discord.Forbidden:
                    await interaction.followup.send("Unable to change nickname", ephemeral=True)

            
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
    # Weekly Reset (ST Only)
    # ---------------------------
    @character.command(name="reset", description="Weekly reset of characters")
    async def reset_all(self, interaction: discord.Interaction):
        """Reset all characters (requires ST role)"""
        await interaction.response.defer(ephemeral=True)

        raw_roles = config.get("ROLES", "[]")
        try:
            allowed_roles = ast.literal_eval(raw_roles)  # safely parse into a list
        except Exception:
            allowed_roles = [r.strip() for r in raw_roles.split(",")]
        user_roles = [r.name for r in getattr(interaction.user, "roles", [])]

        # Role check
        match_found = any(r in user_roles for r in allowed_roles)
        if not match_found:
            await interaction.followup.send("You do not have the correct role!", ephemeral=True)
            return

        chars = get_all_characters()
        try:
            for char in chars:
                c = Character(str_uuid=char["uuid"], user_id=char["user_id"], use_cache=True)
                c.refetch_data()
                c.reset_willpower()
                c.save_parsed()
            await interaction.followup.send("Done!")
        except Exception as e:
            await interaction.followup.send(f"Error occurred {e}")

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
        char.curr_blood = new_blood

        # Log entry
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "delta": delta,
            "comment": comment,
            "result": char.curr_blood,
            "user": str(interaction.user.id),
        }
        char.blood_log.append(entry)
        char.save_parsed()

        # Hunger Torpor trigger
        if char.curr_blood == 0:
            role_names = config.get("ROLES", [])
            guild_roles: list[Role] = interaction.guild.roles
            mentions = " ".join([r.mention for r in guild_roles if r.name in role_names]) or ""
            await interaction.followup.send(
                f"{mentions} ⚠️ {char.name} has exerted too much blood and has fallen into **Hunger Torpor**!",
                ephemeral=False,
            )
            return

        await interaction.followup.send(
            f"✅ {char.name} blood adjusted by {delta} ({comment}). "
            f"Current pool: {char.curr_blood}/{char.max_blood}.",
            ephemeral=True,
        )

    @adjust_blood.autocomplete("name")
    async def adjust_blood_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)


    # ---------------------------
    # Show Blood Logs
    # ---------------------------
    @character.command(name="blood-logs", description="Show recent blood log entries for a character")
    @app_commands.describe(char_id="Pick the character (UUID)")
    async def blood_logs(self, interaction: discord.Interaction, char_id: str):
        """Display recent blood log entries for a character"""
        await interaction.response.defer(ephemeral=False)

        char = Character.load_parsed(char_id)
        if not char:
            await interaction.followup.send("Character not found in database.", ephemeral=True)
            return

        if not hasattr(char, "blood_log") or not char.blood_log:
            await interaction.followup.send(
                f"No blood log found for {getattr(char, 'name', 'Unknown')}.",
                ephemeral=True,
            )
            return

        # Show last 10 entries
        last_entries = char.blood_log[-10:]
        log_text = "\n".join(
            f"[{e['timestamp']}] {'+' if e['delta'] >= 0 else ''}{e['delta']}, "
            f"{e['comment']} → {e['result']} (by <@{e['user']}>)"
            for e in last_entries
        )

        embed = discord.Embed(
            title=f"{char.name} - Blood Log",
            description=f"Recent changes to {char.name}'s blood pool",
            color=discord.Color.red(),
        )
        embed.add_field(name="Log", value=f"```{log_text}```", inline=False)
        embed.set_footer(text=f"UUID: {char.uuid}")

        await interaction.followup.send(embed=embed)


    @blood_logs.autocomplete("char_id")
    async def blood_logs_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            chars = list_all_characters() or []
            logger.debug(f"Autocomplete pulled {len(chars)} chars")
        except Exception as e:
            logger.error(f"Autocomplete error: {e}", exc_info=True)
            return []

        choices: list[app_commands.Choice[str]] = []
        for c in chars:
            try:
                # Defensive: ensure required keys exist
                name = c.get("name", "Unknown")
                uuid = c.get("uuid", "???")
                uid = c.get("user_id")

                member = None
                if interaction.guild and uid:
                    try:
                        member = interaction.guild.get_member(int(uid))
                    except Exception:
                        pass
                username = member.display_name if member else str(uid or "Unknown")

                if current.lower() in name.lower() or current.lower() in uuid.lower():
                    choices.append(
                        app_commands.Choice(
                            name=f"{name} ({username})",
                            value=uuid,
                        )
                    )
            except Exception as inner_e:
                logger.error(f"Error processing character {c}: {inner_e}")

        logger.debug(f"Returning {len(choices)} autocomplete choices")
        return choices[:25]
