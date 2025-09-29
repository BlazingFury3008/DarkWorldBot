import discord
from discord.ext import commands
from libs.database_loader import get_characters_for_user
import logging

logger = logging.getLogger(__name__)


class Tupper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tupper_map = {}  # msg_id -> {"user_id": str, "char_name": str}
        print("Registered Tupper")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        logger.info(f"Message sent: {message.content}")
        user_id = str(message.author.id)

        try:
            chars = get_characters_for_user(user_id)
            if not chars:
                logger.info("No player match")
                return

            for char in chars:
                keyword = char.get("keyword")
                if not keyword:
                    logger.info("No keyword")
                    continue

                if message.content.startswith(f"{keyword}:"):
                    spoken_text = message.content[len(keyword) + 1:].strip()
                    logger.info("Replacing text")
                    try:
                        await message.delete()
                    except discord.Forbidden:
                        logger.warning("Missing permissions to delete messages.")

                    webhook = await message.channel.create_webhook(name=char["name"])
                    sent_msg = await webhook.send(
                        spoken_text,
                        username=char["name"],
                        avatar_url=message.author.display_avatar.url,
                        wait=True,
                    )
                    await webhook.delete()

                    # Add ❌ and 🖊️
                    await sent_msg.add_reaction("❌")
                    await sent_msg.add_reaction("🖊️")

                    # Store mapping
                    self.tupper_map[sent_msg.id] = {
                        "user_id": user_id,
                        "char_name": char["name"],
                    }
                    break

        except Exception as e:
            logger.error(f"Tupper error: {type(e).__name__} - {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        emoji = str(payload.emoji)
        if emoji not in ("❌", "🖊️"):
            return

        msg_id = payload.message_id
        if msg_id not in self.tupper_map:
            return

        data = self.tupper_map[msg_id]
        if str(payload.user_id) != data["user_id"]:
            return  # not the owner

        guild = self.bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id)
        user = guild.get_member(payload.user_id)
        if not channel or not user:
            return

        try:
            msg = await channel.fetch_message(msg_id)
        except discord.NotFound:
            return

        if emoji == "❌":
            await msg.delete()
            del self.tupper_map[msg_id]

        elif emoji == "🖊️":
            try:
                await user.send(
                    f"✏️ You chose to edit your message from **{channel.guild.name}#{channel.name}**.\n"
                    f"Reply here with the new text. (Do not include `{data['char_name']}:`)"
                )

                def check(m):
                    return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)

                new_msg = await self.bot.wait_for("message", check=check, timeout=300)
                await msg.edit(content=new_msg.content)
                await user.send("✅ Your Tupper message was updated!")

            except Exception as e:
                logger.error(f"Edit error: {e}")
                await user.send("⚠️ Failed to edit your Tupper message.")
