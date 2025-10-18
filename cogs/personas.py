import discord
from discord import app_commands
from discord.ext import commands
import uuid as uuid_lib
import io
import json
import logging

from libs.database_loader import (
    create_or_update_persona,
    list_personas_for_user,
    update_persona_keyword,
    update_persona_image,
    delete_persona,
    get_character_by_uuid,
    get_character_uuid_by_name,
    get_characters_for_user,
    execute_query,
)
from libs.character import Character
from libs.personas import (
    render_custom_header,
    generate_default_header,
    get_persona_image,
    parse_header,
)

logger = logging.getLogger(__name__)


class Persona(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tupper_map = {}
        logger.info("Persona Cog Loaded")

    persona = app_commands.Group(
        name="persona",
        description="Manage your personas",
    )

    # ===================================================
    # Autocomplete for persona UUIDs
    # ===================================================
    async def persona_uuid_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete persona UUIDs, showing header as the name."""
        user_id = str(interaction.user.id)
        personas = list_personas_for_user(user_id)
        results = []
        for p in personas:
            display_name = p.get("header") or p.get("uuid", "Unknown Persona")
            if current.lower() in display_name.lower() or current.lower() in p["uuid"].lower():
                results.append(app_commands.Choice(name=display_name, value=p["uuid"]))
        return results[:25]

    # ===================================================
    # /persona new
    # ===================================================
    @persona.command(name="new", description="Create or update a persona linked to your character.")
    @app_commands.describe(
        keyword="Optional keyword to trigger this persona.",
        header_template="Optional custom header template using 'char' as the character object.",
        image="Optional avatar image for this persona.",
    )
    async def persona_new(
        self,
        interaction: discord.Interaction,
        keyword: str = None,
        header_template: str = None,
        image: discord.Attachment = None,
    ):
        user_id = str(interaction.user.id)

        chars = get_characters_for_user(user_id)
        if not chars:
            await interaction.response.send_message(
                "No character found. Please set up a character first.",
                ephemeral=True,
            )
            return

        char_uuid = get_character_uuid_by_name(user_id, chars[0]["name"])
        character_data = get_character_by_uuid(char_uuid)
        if not character_data:
            await interaction.response.send_message(
                "Could not load your character data.",
                ephemeral=True,
            )
            return

        header = (
            render_custom_header(header_template, character_data)
            if header_template
            else generate_default_header(character_data)
        )

        image_bytes = await image.read() if image else None

        persona_uuid = str(uuid_lib.uuid4())
        create_or_update_persona(
            uuid=persona_uuid,
            user_id=user_id,
            header=header,
            keyword=keyword,
            image=image_bytes,
        )

        await interaction.response.send_message(
            f"Persona created successfully.\nHeader:\n**{header}**\nUUID: `{persona_uuid}`",
            ephemeral=True,
        )

    # ===================================================
    # /persona keyword
    # ===================================================
    @persona.command(name="keyword", description="Update the keyword for an existing persona.")
    @app_commands.describe(persona_uuid="UUID of the persona", new_keyword="New keyword to trigger the persona.")
    @app_commands.autocomplete(persona_uuid=persona_uuid_autocomplete)
    async def persona_keyword(
        self,
        interaction: discord.Interaction,
        persona_uuid: str,
        new_keyword: str,
    ):
        user_id = str(interaction.user.id)
        update_persona_keyword(persona_uuid, user_id, new_keyword)
        await interaction.response.send_message(
            f"Persona keyword updated to `{new_keyword}`.",
            ephemeral=True,
        )

    # ===================================================
    # /persona image
    # ===================================================
    @persona.command(name="image", description="Update the image/avatar for a persona.")
    @app_commands.describe(persona_uuid="UUID of the persona", new_image="The new image to use.")
    @app_commands.autocomplete(persona_uuid=persona_uuid_autocomplete)
    async def persona_image(
        self,
        interaction: discord.Interaction,
        persona_uuid: str,
        new_image: discord.Attachment,
    ):
        user_id = str(interaction.user.id)
        image_bytes = await new_image.read()
        update_persona_image(persona_uuid, user_id, image_bytes)
        await interaction.response.send_message(
            "Persona image updated.",
            ephemeral=True,
        )

    # ===================================================
    # /persona header
    # ===================================================
    @persona.command(name="header", description="Update the header template for a persona.")
    @app_commands.describe(
        persona_uuid="UUID of the persona.",
        header_template="New header template using 'char' as the character object.",
    )
    @app_commands.autocomplete(persona_uuid=persona_uuid_autocomplete)
    async def persona_header(
        self,
        interaction: discord.Interaction,
        persona_uuid: str,
        header_template: str,
    ):
        user_id = str(interaction.user.id)
        char = Character.load_for_user(user_id)

        if not char:
            await interaction.response.send_message("No character found to render the header.", ephemeral=True)
            return

        parsed = parse_header(header_template, char.to_dict())
        if parsed is None:
            await interaction.response.send_message("Header template formatting error.", ephemeral=True)
            return

        execute_query(
            "UPDATE persona SET header = ? WHERE uuid = ? AND user_id = ?",
            (header_template, persona_uuid, user_id),
            commit=True,
        )

        rendered = render_custom_header(header_template, char.to_dict())
        await interaction.response.send_message(
            f"Persona header updated to:\n**{rendered}**",
            ephemeral=True,
        )

    # ===================================================
    # /persona delete
    # ===================================================
    @persona.command(name="delete", description="Delete a persona.")
    @app_commands.describe(persona_uuid="UUID of the persona to delete.")
    @app_commands.autocomplete(persona_uuid=persona_uuid_autocomplete)
    async def persona_delete(
        self,
        interaction: discord.Interaction,
        persona_uuid: str,
    ):
        user_id = str(interaction.user.id)
        delete_persona(persona_uuid, user_id)
        await interaction.response.send_message("Persona deleted.", ephemeral=True)

    # ===================================================
    # /persona list
    # ===================================================
    @persona.command(name="list", description="List all of your personas.")
    async def persona_list(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        personas = list_personas_for_user(user_id)
        if not personas:
            await interaction.response.send_message("You have no personas registered.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Personas",
            color=discord.Color.blurple(),
        )
        for p in personas:
            embed.add_field(
                name=p["header"],
                value=f"UUID: `{p['uuid']}`\nKeyword: `{p.get('keyword', 'None')}`",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ===================================================
    # /persona json
    # ===================================================
    @persona.command(name="json", description="Export your character JSON to your DMs.")
    async def persona_json(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        chars = get_characters_for_user(user_id)
        if not chars:
            await interaction.response.send_message("No character found to export.", ephemeral=True)
            return

        char_uuid = get_character_uuid_by_name(user_id, chars[0]["name"])
        character_data = get_character_by_uuid(char_uuid)
        if not character_data:
            await interaction.response.send_message("Character not found.", ephemeral=True)
            return

        json_bytes = json.dumps(character_data, indent=4).encode("utf-8")
        file = discord.File(io.BytesIO(json_bytes), filename=f"{character_data['name']}_{char_uuid}.json")

        try:
            await interaction.user.send("Here is the exported JSON for your character.", file=file)
            await interaction.response.send_message("Character JSON has been sent to your DMs.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I couldn't send you a DM. Please enable DMs from server members.",
                ephemeral=True,
            )

    # ===================================================
    # Message Listener (Keyword Relay)
    # ===================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        user_id = str(message.author.id)
        content = message.content.strip()
        personas = list_personas_for_user(user_id)
        char = Character.load_for_user(user_id)

        if not personas or not char:
            return

        for persona_entry in personas:
            keyword = persona_entry.get("keyword")
            if not keyword:
                continue

            trigger = f"{keyword}:"
            if content.lower().startswith(trigger.lower()):
                spoken_text = content[len(trigger):].strip()

                try:
                    await message.delete()
                except discord.Forbidden:
                    logger.warning("Missing permissions to delete messages.")

                header_text = parse_header(persona_entry["header"], char.to_dict()) or persona_entry["header"]
                full_message = f"{header_text}\n{spoken_text}"

                avatar_bytes = get_persona_image(persona_entry["uuid"])
                username = persona_entry.get("header", "Persona")

                try:
                    webhook = await message.channel.create_webhook(
                        name=username,
                        avatar=avatar_bytes if avatar_bytes else None,
                    )
                    sent_msg = await webhook.send(full_message, username=username, wait=True)
                    await webhook.delete()

                    self.tupper_map[sent_msg.id] = {
                        "user_id": user_id,
                        "persona_name": username,
                    }
                except Exception as e:
                    logger.error(f"Failed to send persona message: {e}")
                break


# ===================================================
# Setup Function
# ===================================================
async def setup(bot: commands.Bot):
    await bot.add_cog(Persona(bot))
