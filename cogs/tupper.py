import discord
from discord.ext import commands
from libs.database_loader import get_characters_for_user
import logging

logger = logging.getLogger(__name__)


class Tupper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tupper_map = {}  # msg_id -> {"user_id": str, "char_name": str}
        logging.info("Registered Tupper")

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

                    # Store mapping
                    self.tupper_map[sent_msg.id] = {
                        "user_id": user_id,
                        "char_name": char["name"],
                    }
                    break

        except Exception as e:
            logger.error(f"Tupper error: {type(e).__name__} - {e}")
