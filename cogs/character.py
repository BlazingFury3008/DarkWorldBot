import discord
from discord.ext import commands
from discord import app_commands
from libs.character import *
import logging
from bot import config
import ast

logger = logging.getLogger(__name__)

# ---- Autocomplete helper ----





class CharacterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("Registered CharacterCog")

    character = app_commands.Group(
        name="character", description="All character commands"
    )

    async def _character_name_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
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

    @character.command(name="init", description="Add A Character")
    async def init(self, interaction: discord.Interaction, url: str):
        """Initialise a character into the database"""
        await interaction.response.defer(ephemeral=True)
        try:
            user_id = str(interaction.user.id)
            char = Character(user_id=user_id, SHEET_URL=url)
            char.reset_temp()
            logger.info("Character Fetched")

            keyword = (char.name or char.uuid).lower().replace(" ", "")
            val = char.save_parsed(keyword=keyword, update=False)

            if val == -1:
                await interaction.followup.send("Character already saved!", ephemeral=True)
                return

            base_username = interaction.user.name
            new_nick = f"{char.name} || {base_username}"

            member = interaction.user
            if isinstance(member, discord.Member):
                try:
                    await member.edit(nick=new_nick)
                except discord.Forbidden:
                        message = "Character saved, but I don't have permission to change your nickname.",
    
                    

            await interaction.followup.send(
                f"Saved and set nickname to **{new_nick}**\n"
                f"Keyword for Tuppers: **{keyword}** \n {message}",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    
    # -- Show Character -- #

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

            embed = discord.Embed(
                title=f"{char.name or 'Unknown'}",
                description=f"Player: {char.player_name or 'Unknown'}",
                color=discord.Color.dark_red(),
            )
            embed.add_field(
                name="Clan", value=char.clan or "Unknown", inline=True)
            embed.add_field(name="Generation", value=str(
                char.generation or "?"), inline=True)
            embed.add_field(
                name="Sect", value=char.sect or "Unknown", inline=True)

            embed.add_field(
                name="Concept", value=char.concept or "Unknown", inline=False)
            embed.add_field(
                name="Nature/Demeanor", value=f"{char.nature or '?'} / {char.demeanor or '?'}", inline=False)
            embed.add_field(
                name="Bane", value=char.bane or "None", inline=False)

            embed.add_field(name=" Willpower", 
                            value=f'{str(char.curr_willpower or 0)}/{str(char.max_willpower or 0)}', inline=True)
            embed.add_field(
                name="Blood Pool", value=f"{char.curr_blood or '?'}/{char.max_blood or '?'} (Blood Per Turn: {char.blood_per_turn or '?'})", inline=True)

            if char.disciplines:
                disc_text = "\n".join(
                    f"**{d['name']}** {d['value']}" for d in char.disciplines)
                embed.add_field(name="Disciplines",
                                value=disc_text[:1024], inline=False)

            if char.backgrounds:
                back_text = "\n".join(
                    f"**{b['name']}** {b['value']}" for b in char.backgrounds)
                embed.add_field(name="Backgrounds",
                                value=back_text[:1024], inline=False)

            if char.merits:
                merits_text = "\n".join(
                    f"{m['name']} ({m['rating']}pt)" for m in char.merits)
                embed.add_field(
                    name="Merits", value=merits_text[:1024], inline=False)

            if char.flaws:
                flaws_text = "\n".join(
                    f"{f['name']} ({f['rating']}pt)" for f in char.flaws)
                embed.add_field(
                    name="Flaws", value=flaws_text[:1024], inline=False)

            embed.set_footer(text=f"User: {interaction.user.display_name}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    @show.autocomplete("name")
    async def show_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)

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
            await interaction.followup.send("Resynced successfully!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(
                f"There was an error: `{type(e).__name__}: {e}`", ephemeral=True
            )

    @resync.autocomplete("name")
    async def resync_autocomplete(self, interaction: discord.Interaction, current: str):
        return await self._character_name_autocomplete(interaction, current)

    @character.command(name="keyword", description="Edit your character's keyword")
    @app_commands.describe(name="Character to update", new_keyword="New keyword to assign")
    async def keyword(
        self,
        interaction: discord.Interaction,
        name: str,
        new_keyword: str
    ):
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


    @character.command(name="reset", description="Weekly reset of characters")
    async def reset_all(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        raw_roles = config.get("ROLES", "[]")
        try:
            allowed_roles = ast.literal_eval(raw_roles)  # safely parse into a list
        except Exception:
            allowed_roles = [r.strip() for r in raw_roles.split(",")]
        user_roles = [r.name for r in getattr(interaction.user, "roles", [])]

        logger.info(f"[RESET] Allowed roles: {allowed_roles}")
        logger.info(f"[RESET] User {interaction.user} roles: {user_roles}")

        # Check each comparison explicitly
        match_found = False
        for allowed in allowed_roles:
            for user_role in user_roles:
                logger.debug(f"[RESET] Comparing allowed '{allowed}' with user role '{user_role}'")
                if allowed == user_role:
                    logger.info(f"[RESET] Match found: '{allowed}'")
                    match_found = True

        if not match_found:
            logger.warning(f"[RESET] User {interaction.user} has no matching roles.")
            await interaction.followup.send("You do not have the correct role!", ephemeral=True)
            return

        logger.info(f"[RESET] User {interaction.user} passed role check.")
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
                

        
